#!/usr/bin/env python3
"""Essais de l'intégration timed_cover (Custom Cover Position) dans la VM ha-sandbox, par l'API de Home Assistant.

Le script crée des volets à temps de trajet autour des faux volets de l'intégration
`demo`, les actionne et vérifie les positions et les appareils. Il ne touche à rien
d'autre : les entrées créées sont supprimées à la fin (sauf avec --garder).

Prérequis : jeton dans ~/.ha-sandbox-token (jamais affiché), sandbox joignable,
intégration `demo` active, intégration timed_cover déployée (tools/deployer-sandbox.sh).

Usage : python3 tools/essai_sandbox.py [--garder]
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "http://10.10.30.30"
JETON = Path.home().joinpath(".ha-sandbox-token").read_text().strip()

# Faux volets de l'intégration demo : celui de la cuisine n'a pas de position (ouvrir,
# fermer, arrêter seulement), exactement comme un volet Overkiz. La porte de garage de
# demo n'est pas utilisée : elle ne sait pas s'arrêter.
SOURCES = {
    "cuisine": "cover.kitchen_window",
    "couloir": "cover.hall_window",
    "salon": "cover.living_room_window",
}
TEMPS_MONTEE = 10.0
TEMPS_DESCENTE = 8.0

resultats: list[tuple[str, bool, str]] = []


def api(methode: str, chemin: str, corps: dict | None = None):
    """Appelle l'API de Home Assistant ; renvoie le JSON (ou le texte) de la réponse."""
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(URL + chemin, data=donnees, method=methode)
    requete.add_header("Authorization", f"Bearer {JETON}")
    requete.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(requete, timeout=30) as reponse:
            texte = reponse.read().decode()
    except urllib.error.HTTPError as erreur:
        texte = erreur.read().decode()
        raise RuntimeError(f"{methode} {chemin} -> HTTP {erreur.code} : {texte[:300]}") from None
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        return texte


def etat(entity_id: str) -> dict:
    return api("GET", f"/api/states/{entity_id}")


def modele(texte: str) -> str:
    return str(api("POST", "/api/template", {"template": texte})).strip()


def service(domaine: str, nom: str, **donnees) -> None:
    api("POST", f"/api/services/{domaine}/{nom}", donnees)


def verifier(nom: str, condition: bool, detail: str = "") -> None:
    resultats.append((nom, condition, detail))
    print(f"  [{'OK ' if condition else 'ÉCHEC'}] {nom}" + (f" — {detail}" if detail else ""))


def creer_volet(cle: str, source: str, nom: str | None = None, **reglages) -> str:
    """Crée un ouvrant à position estimée par les étapes de configuration ; renvoie son entry_id."""
    if "presets" in reglages:  # le formulaire range la liste dans le bloc « positions »
        reglages["positions"] = {"presets": reglages.pop("presets")}
    flux = api("POST", "/api/config/config_entries/flow", {"handler": "timed_cover"})
    flux = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"source_entity": source})
    assert flux["step_id"] == "parametres", flux
    flux = api(
        "POST",
        f"/api/config/config_entries/flow/{flux['flow_id']}",
        {
            "name": nom or f"Essai {cle}",
            "travel_time_up": TEMPS_MONTEE,
            "travel_time_down": TEMPS_DESCENTE,
            "send_stop_at_ends": False,
            "device_class": "shutter",
            "hide_source": True,
            "take_over": True,
            "source_suffix": "source",
            **reglages,
        },
    )
    assert flux["type"] == "create_entry", flux
    return flux["result"]["entry_id"]


def identifiant(cle: str) -> str:
    return f"cover.essai_{cle}"


def attendre_etat(entity_id: str, attendu: str, delai: float) -> float:
    """Attend qu'une entité prenne un état ; renvoie le temps mis (ou -1)."""
    debut = time.monotonic()
    while time.monotonic() - debut < delai:
        if etat(entity_id)["state"] == attendu:
            return time.monotonic() - debut
        time.sleep(0.2)
    return -1.0


def position(entity_id: str) -> int | None:
    return etat(entity_id)["attributes"].get("current_position")


def favoris(entity_id: str):
    """Favoris de la fenêtre de l'ouvrant (options du registre), ou None s'ils sont par défaut."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    from ws_registre import options_cover
    return options_cover(entity_id).get("favorite_positions")


def bloc_ouvert(entry_id: str) -> bool:
    """Le bloc « positions » du formulaire de réglages est-il annoncé ouvert à l'interface ?"""
    f = api("POST", "/api/config/config_entries/options/flow", {"handler": entry_id})
    bloc = next(c for c in f["data_schema"] if c["name"] == "positions")
    api("DELETE", "/api/config/config_entries/options/flow/" + f["flow_id"])
    return bool(bloc["expanded"])


def existe(entity_id: str) -> bool:
    try:
        etat(entity_id)
        return True
    except RuntimeError:
        return False


# Titres des seules entrées que ce script crée (et supprime) : les vrais ouvrants de la sandbox,
# par exemple ceux d'Overkiz, ne doivent jamais être touchés.
TITRES_ESSAI = {"Essai cuisine", "Essai couloir", "Essai salon", "Hall Window"}


def nettoyer() -> None:
    for entree in api("GET", "/api/config/config_entries/entry"):
        if entree["domain"] == "timed_cover" and entree["title"] in TITRES_ESSAI:
            api("DELETE", f"/api/config/config_entries/entry/{entree['entry_id']}")


def main() -> int:
    garder = "--garder" in sys.argv
    print("Nettoyage préalable des anciens essais...")
    nettoyer()
    time.sleep(1)
    # Remet les faux volets dans un état connu.
    for source in SOURCES.values():
        service("cover", "stop_cover", entity_id=source)

    print("\n1. Création de 3 volets à temps de trajet (montée 10 s, descente 8 s)")
    entrees = {cle: creer_volet(cle, src) for cle, src in SOURCES.items()}
    time.sleep(2)
    # La dernière position connue est restaurée (comme après un redémarrage) : on part de 0.
    for cle in SOURCES:
        service("timed_cover", "set_known_position", entity_id=identifiant(cle), position=0)
    for cle in SOURCES:
        e = etat(identifiant(cle))
        verifier(f"{identifiant(cle)} existe", e["state"] != "unavailable", e["state"])

    print("\n2. Rattachement à l'appareil du volet réel")
    for cle, source in SOURCES.items():
        meme = modele(
            f"{{{{ device_id('{identifiant(cle)}') == device_id('{source}') "
            f"and device_id('{source}') is not none }}}}"
        )
        verifier(f"{identifiant(cle)} sous l'appareil de {source}", meme == "True")

    print("\n2 bis. Nom, identifiant et masquage du volet d'origine")
    for cle, source in SOURCES.items():
        nom = etat(identifiant(cle))["attributes"].get("friendly_name")
        verifier(f"nom affiché de {identifiant(cle)} = « Essai {cle} »", nom == f"Essai {cle}", f"{nom}")
        masque = modele(f"{{{{ is_hidden_entity('{source}') }}}}")
        verifier(f"le volet d'origine {source} est masqué", masque == "True", masque)

    print("\n3. Attributs de l'entité")
    attrs = etat(identifiant("cuisine"))["attributes"]
    verifier("source_entity", attrs.get("source_entity") == SOURCES["cuisine"])
    verifier("temps de montée / descente", attrs.get("travel_time_up") == TEMPS_MONTEE and attrs.get("travel_time_down") == TEMPS_DESCENTE)
    verifier("state assumé et fonctions 15", attrs.get("assumed_state") is True and attrs.get("supported_features") == 15)

    cuisine = identifiant("cuisine")
    print("\n4. Ouverture complète (10 s attendues)")
    service("cover", "open_cover", entity_id=cuisine)
    time.sleep(0.6)
    verifier("état « opening » pendant le trajet", etat(cuisine)["state"] == "opening", etat(cuisine)["state"])
    time.sleep(4.4)
    p = position(cuisine)
    verifier("position à mi-parcours ≈ 50", p is not None and 42 <= p <= 58, f"{p}")
    duree = attendre_etat(cuisine, "open", 12)
    verifier("état « open » à la fin", duree > 0, f"{duree:.1f} s de plus")
    verifier("position finale 100", position(cuisine) == 100, f"{position(cuisine)}")

    print("\n5. Position intermédiaire : de 100 à 40 (descente, 60 % de 8 s = 4,8 s)")
    debut = time.monotonic()
    service("cover", "set_cover_position", entity_id=cuisine, position=40)
    time.sleep(1.0)
    verifier("état « closing » pendant le trajet", etat(cuisine)["state"] == "closing", etat(cuisine)["state"])
    verifier("attribut target_position = 40", etat(cuisine)["attributes"].get("target_position") == 40)
    attendre_etat(cuisine, "open", 8)  # « open » = immobile et position > 0
    ecoule = time.monotonic() - debut
    verifier("arrivée en ≈ 4,8 s", 4.2 <= ecoule <= 6.0, f"{ecoule:.1f} s")
    verifier("position finale 40", position(cuisine) == 40, f"{position(cuisine)}")

    print("\n6. Demi-tour en cours de route : cible 90 puis, 1 s après, cible 10")
    service("cover", "set_cover_position", entity_id=cuisine, position=90)
    time.sleep(1.0)
    p_avant = position(cuisine)
    service("cover", "set_cover_position", entity_id=cuisine, position=10)
    time.sleep(0.8)
    verifier("le volet descend après le demi-tour", etat(cuisine)["state"] == "closing", f"{etat(cuisine)['state']} (position {position(cuisine)}, avant {p_avant})")
    time.sleep(6.5)
    verifier("position finale 10", position(cuisine) == 10, f"{position(cuisine)}")

    print("\n7. Arrêt au milieu d'un déplacement")
    service("cover", "open_cover", entity_id=cuisine)
    time.sleep(3.0)
    service("cover", "stop_cover", entity_id=cuisine)
    p1 = position(cuisine)
    time.sleep(2.0)
    p2 = position(cuisine)
    verifier("la position se fige après l'arrêt", p1 == p2 and etat(cuisine)["state"] in ("open", "closed"), f"{p1} puis {p2}, état {etat(cuisine)['state']}")

    print("\n8. Disponibilité : le volet réel devient indisponible")
    reel = SOURCES["cuisine"]
    ancien = etat(reel)
    api("POST", f"/api/states/{reel}", {"state": "unavailable", "attributes": ancien["attributes"]})
    time.sleep(1.0)
    verifier("le volet à temps de trajet devient indisponible", etat(cuisine)["state"] == "unavailable", etat(cuisine)["state"])
    api("POST", f"/api/states/{reel}", {"state": ancien["state"], "attributes": ancien["attributes"]})
    time.sleep(1.0)
    verifier("il redevient disponible", etat(cuisine)["state"] != "unavailable", etat(cuisine)["state"])
    api("POST", f"/api/states/{reel}", {"state": "unknown", "attributes": ancien["attributes"]})
    time.sleep(1.0)
    verifier("l'état « inconnu » du volet réel (RTS) reste disponible", etat(cuisine)["state"] != "unavailable", etat(cuisine)["state"])
    api("POST", f"/api/states/{reel}", {"state": ancien["state"], "attributes": ancien["attributes"]})

    print("\n9. Un script actionne les 3 volets en même temps (le cas qui posait problème)")
    tous = [identifiant(c) for c in SOURCES]
    for t in tous:
        service("timed_cover", "set_known_position", entity_id=t, position=0)
    service("cover", "open_cover", entity_id=tous)
    debut = time.monotonic()
    while time.monotonic() - debut < 14 and not all(position(t) == 100 for t in tous):
        time.sleep(0.3)
    verifier("les 3 volets sont ouverts à 100", all(position(t) == 100 for t in tous), f"{time.monotonic() - debut:.1f} s, positions {[position(t) for t in tous]}")
    service("cover", "set_cover_position", entity_id=tous, position=40)
    time.sleep(1.0)
    verifier("les 3 volets descendent en même temps", all(etat(t)["state"] == "closing" for t in tous), str([etat(t)["state"] for t in tous]))
    time.sleep(6.5)
    positions = [position(t) for t in tous]
    verifier("les 3 volets sont à 40 sans interférence", all(p == 40 for p in positions), str(positions))
    service("cover", "close_cover", entity_id=tous)
    time.sleep(6.0)
    time.sleep(3.5)
    verifier("fermeture simultanée : les 3 volets à 0", all(position(t) == 0 for t in tous), str([position(t) for t in tous]))

    print("\n10. Recalage par le service set_known_position")
    service("timed_cover", "set_known_position", entity_id=cuisine, position=70)
    time.sleep(0.5)
    verifier("position recalée à 70 sans mouvement", position(cuisine) == 70 and etat(cuisine)["state"] == "open", f"{position(cuisine)}")

    print("\n11. Modification des temps par le formulaire d'options")
    verifier("sans position, le bloc « Positions prédéfinies » est replié", not bloc_ouvert(entrees["cuisine"]))
    flux = api("POST", "/api/config/config_entries/options/flow", {"handler": entrees["cuisine"]})
    flux = api(
        "POST",
        f"/api/config/config_entries/options/flow/{flux['flow_id']}",
        {"travel_time_up": 20, "travel_time_down": 16, "send_stop_at_ends": True, "device_class": "blind", "hide_source": True, "disable_other_entities": False, "positions": {"presets": []}},
    )
    time.sleep(2.0)
    attrs = etat(cuisine)["attributes"]
    verifier("nouveaux temps pris en compte", attrs.get("travel_time_up") == 20 and attrs.get("travel_time_down") == 16, f"{attrs.get('travel_time_up')}/{attrs.get('travel_time_down')}")
    verifier("la position est conservée après le rechargement", position(cuisine) == 70, f"{position(cuisine)}")
    verifier("type de volet modifié", attrs.get("device_class") == "blind", f"{attrs.get('device_class')}")

    if not garder:
        print("\nNettoyage : suppression des entrées d'essai")
        nettoyer()
        time.sleep(2)
        for cle, source in SOURCES.items():
            masque = modele(f"{{{{ is_hidden_entity('{source}') }}}}")
            verifier(f"{source} de nouveau visible après suppression", masque == "False", masque)

    print("\n12. Échange des noms : l'ouvrant « Hall Window » reprend l'identifiant de cover.hall_window")
    nettoyer()
    time.sleep(2)
    source = "cover.hall_window"
    creer_volet("couloir", source, nom="Hall Window")
    time.sleep(2.5)
    origine = "cover.hall_window_source"
    nouveau = etat(source)
    verifier("l'identifiant d'origine est repris par le nouvel ouvrant", nouveau["attributes"].get("travel_time_up") == TEMPS_MONTEE, str(nouveau["attributes"].get("travel_time_up")))
    verifier("le nouvel ouvrant pointe vers l'ouvrant d'origine renommé", nouveau["attributes"].get("source_entity") == origine, str(nouveau["attributes"].get("source_entity")))
    verifier("nom du nouvel ouvrant = « Hall Window »", nouveau["attributes"].get("friendly_name") == "Hall Window", str(nouveau["attributes"].get("friendly_name")))
    verifier("l'ouvrant d'origine existe sous son nouvel identifiant", existe(origine))
    if existe(origine):
        verifier("nom de l'ouvrant d'origine = « Hall Window (source) »", etat(origine)["attributes"].get("friendly_name") == "Hall Window (source)", str(etat(origine)["attributes"].get("friendly_name")))
        verifier("l'ouvrant d'origine est masqué", modele(f"{{{{ is_hidden_entity('{origine}') }}}}") == "True")
        service("timed_cover", "set_known_position", entity_id=source, position=100)
        service("cover", "close_cover", entity_id=source)
        time.sleep(1.0)
        verifier("un ordre au nouvel ouvrant atteint bien l'ouvrant d'origine", etat(origine)["state"] in ("closing", "closed"), etat(origine)["state"])
    nettoyer()
    time.sleep(2.5)
    verifier("à la suppression, l'identifiant d'origine est rendu à l'ouvrant d'origine", existe(source) and "travel_time_up" not in etat(source)["attributes"], str(existe(source)))
    verifier("à la suppression, le nom d'origine est remis", existe(source) and etat(source)["attributes"].get("friendly_name") == "Hall Window", str(etat(source)["attributes"].get("friendly_name")) if existe(source) else "absent")
    verifier("à la suppression, l'identifiant temporaire disparaît", not existe(origine))
    verifier("à la suppression, l'ouvrant d'origine est de nouveau visible", modele(f"{{{{ is_hidden_entity('{source}') }}}}") == "False")

    print("\n13. Sans échange des noms : le nouvel ouvrant reçoit un identifiant différent")
    creer_volet("couloir", source, nom="Hall Window", take_over=False)
    time.sleep(2.5)
    verifier("le nouvel ouvrant devient cover.hall_window_2", existe("cover.hall_window_2"))
    verifier("l'ouvrant d'origine garde son identifiant et son nom", existe(source) and etat(source)["attributes"].get("friendly_name") == "Hall Window" and "travel_time_up" not in etat(source)["attributes"])
    nettoyer()
    time.sleep(2.0)

    print("\n14. Positions prédéfinies : un bouton par ligne, rangé sous l'appareil d'origine")
    entree = creer_volet(
        "couloir", source, nom="Hall Window",
        presets=[{"name": "Chaleur", "position": 33}, {"name": "Pare-soleil", "position": 60}],
    )
    time.sleep(2.5)
    verifier("les favoris de l'ouvrant deviennent 0, 33, 60, 100", favoris("cover.hall_window") == [0, 33, 60, 100], str(favoris("cover.hall_window")))
    # Le formulaire rouvert doit annoncer la liste existante comme valeur par défaut du bloc.
    f = api("POST", "/api/config/config_entries/options/flow", {"handler": entree})
    bloc = next(c for c in f["data_schema"] if c["name"] == "positions")
    api("DELETE", "/api/config/config_entries/options/flow/" + f["flow_id"])
    noms = [p["name"] for p in (bloc.get("default") or {}).get("presets", [])]
    verifier("rouvrir les réglages : la liste existante est reprise par le bloc", noms == ["Chaleur", "Pare-soleil"], str(noms))
    verifier("avec des positions, le bloc est ouvert", bloc_ouvert(entree))
    chaleur, soleil = "button.hall_window_chaleur", "button.hall_window_pare_soleil"
    verifier("les deux boutons existent", existe(chaleur) and existe(soleil))
    if existe(chaleur):
        nom_b = etat(chaleur)["attributes"].get("friendly_name")
        verifier("nom du bouton = « Hall Window Chaleur »", nom_b == "Hall Window Chaleur", str(nom_b))
        meme = modele(f"{{{{ device_id('{chaleur}') == device_id('{origine}') and device_id('{origine}') is not none }}}}")
        verifier("le bouton est sous l'appareil d'origine", meme == "True", meme)
        service("timed_cover", "set_known_position", entity_id=source, position=0)
        service("button", "press", entity_id=chaleur)
        time.sleep(1.0)
        verifier("l'appui met l'ouvrant en mouvement", etat(source)["state"] == "opening", etat(source)["state"])
        time.sleep(4.0)
        verifier("l'ouvrant arrive à 33 % (3,3 s sur 10 s)", position(source) == 33, str(position(source)))
        verifier("l'ouvrant d'origine a bien reçu les ordres (arrêté)", etat(origine)["state"] in ("open", "closed", "opening"), etat(origine)["state"])

    print("\n15. Gestion des positions par les réglages")
    def options(donnees: dict) -> dict:
        f = api("POST", "/api/config/config_entries/options/flow", {"handler": entree})
        return api("POST", f"/api/config/config_entries/options/flow/{f['flow_id']}", donnees)
    base = {"travel_time_up": TEMPS_MONTEE, "travel_time_down": TEMPS_DESCENTE, "send_stop_at_ends": False,
            "device_class": "shutter", "hide_source": True, "disable_other_entities": False}
    res = options({**base, "positions": {"presets": [{"name": "A", "position": 10}, {"name": "a", "position": 20}]}})
    verifier("deux positions de même nom refusées", res.get("errors", {}).get("positions") == "noms_en_double", str(res.get("errors")))
    res = options({**base, "positions": {"presets": [{"name": f"P{i}", "position": i * 10} for i in range(9)]}})
    verifier("plus de 8 positions refusées", res.get("errors", {}).get("positions") == "trop_de_positions", str(res.get("errors")))
    try:
        options({**base, "positions": {"presets": [{"name": "B", "position": 150}]}})
        refusee = False
    except RuntimeError as erreur:  # Home Assistant refuse lui-même la valeur (HTTP 400)
        refusee = "too large" in str(erreur)
    verifier("position hors de 0 à 100 refusée", refusee)
    res = options({**base, "positions": {"presets": [{"name": "Pare-soleil", "position": 60, "icon": "mdi:weather-sunny"}]}})
    time.sleep(3.0)
    verifier("une position retirée : son bouton disparaît", not existe(chaleur) and existe(soleil))
    verifier("l'icône choisie est appliquée au bouton", etat(soleil)["attributes"].get("icon") == "mdi:weather-sunny", str(etat(soleil)["attributes"].get("icon")))
    verifier("les favoris de l'ouvrant suivent la position restante (0, 60, 100)", favoris(source) == [0, 60, 100], str(favoris(source)))
    res = options({**base, "positions": {"presets": []}})
    time.sleep(3.0)
    verifier("sans position, les favoris par défaut reviennent", favoris(source) is None, str(favoris(source)))
    res = options({**base, "positions": {"presets": [{"name": "Pare-soleil", "position": 60}]}})
    time.sleep(3.0)
    nettoyer()
    time.sleep(2.5)
    verifier("à la suppression, plus aucun bouton", not existe(soleil))

    print("\n16. Diagnostic de l'ouvrant (Télécharger les diagnostics)")
    entree = creer_volet("cuisine", SOURCES["cuisine"])
    time.sleep(2.5)
    diag = api("GET", f"/api/diagnostics/config_entry/{entree}")
    d = diag.get("data", {})
    verifier("le diagnostic existe et donne la version", d.get("versions", {}).get("integration") is not None, str(d.get("versions")))
    verifier("il contient la configuration (temps d'ouverture)", d.get("config_entry", {}).get("data", {}).get("travel_time_up") == TEMPS_MONTEE)
    verifier("il contient l'état de l'ouvrant", (d.get("cover", {}).get("state") or {}).get("state") is not None, str((d.get("cover", {}).get("state") or {}).get("state")))
    verifier("il contient l'ouvrant d'origine et son registre", (d.get("source_cover", {}).get("registry") or {}).get("entity_id") == SOURCES["cuisine"])
    verifier("les noms de champs du diagnostic sont sans accent", all(k.isascii() for k in d.keys()) and all(k.isascii() for k in d["config_entry"].keys()), str(list(d.keys())))
    verifier("aucun secret dans le diagnostic", not any(m in json.dumps(diag).lower() for m in ("password", "token", "bearer")))
    nettoyer()
    time.sleep(2.0)

    print("\n17. Textes : messages d'erreur du code traduits, suffixe proposé")
    sys.path.insert(0, str(Path(__file__).parent))
    from ws_registre import traductions
    en = traductions("en", "exceptions"); fr = traductions("fr", "exceptions")
    msg_en = en.get("component.timed_cover.exceptions.source_unavailable.message", "")
    msg_fr = fr.get("component.timed_cover.exceptions.source_unavailable.message", "")
    verifier("message d'erreur en anglais", "is unavailable" in msg_en, msg_en)
    verifier("message d'erreur en français", "indisponible" in msg_fr, msg_fr)
    verifier("second message traduit (français)", "introuvable" in fr.get("component.timed_cover.exceptions.cover_not_found.message", ""))
    f = api("POST", "/api/config/config_entries/flow", {"handler": "timed_cover"})
    f = api("POST", f"/api/config/config_entries/flow/{f['flow_id']}", {"source_entity": SOURCES["cuisine"]})
    defaut = next(c for c in f["data_schema"] if c["name"] == "source_suffix").get("default")
    api("DELETE", "/api/config/config_entries/flow/" + f["flow_id"])
    verifier("suffixe proposé : « source » (sandbox en français)", defaut == "source", str(defaut))

    echecs = [r for r in resultats if not r[1]]
    print(f"\nRésultat : {len(resultats) - len(echecs)}/{len(resultats)} vérifications réussies.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
