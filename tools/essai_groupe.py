#!/usr/bin/env python3
"""Essais du groupe de volets de timed_cover (Custom Cover Position) dans la VM ha-sandbox.

Sept faux volets (intégration `essai_volets`, qui note l'instant où chaque ordre est reçu et met 1 s
à l'accepter) sont enrobés par l'intégration, avec des positions prédéfinies différentes, puis réunis
dans un groupe créé par le formulaire. Le script vérifie : le nom, l'appareil et les boutons du
groupe, les ordres envoyés en parallèle (instants de réception), les positions de chaque volet, un volet
indisponible, la modification des volets du groupe, l'ajout d'une position à un volet, la suppression
d'un volet puis du groupe.

Prérequis : jeton dans ~/.ha-sandbox-token (jamais affiché), intégrations timed_cover et essai_volets
déployées dans la sandbox. Ne touche qu'aux entrées « Essai volet N » et « Essai groupe » : jamais aux
vrais volets (Overkiz) de la sandbox, qui sont reliés au compte cloud de Sophie.

Usage : python3 tools/essai_groupe.py [--garder]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import essai_sandbox as base  # noqa: E402  (jeton, appels API, vérifications communes)
from essai_sandbox import api, etat, existe, modele, service, verifier  # noqa: E402
from essai_parallele import journal  # noqa: E402

NOMBRE = 7
ORIGINES = [f"cover.essai_volet_{n}" for n in range(1, NOMBRE + 1)]  # faux volets, avant l'échange
VOLETS = list(ORIGINES)  # après l'échange, ces identifiants sont ceux des volets à temps de trajet
GROUPE = "cover.essai_groupe"
TITRES = {f"Essai volet {n}" for n in range(1, NOMBRE + 2)} | {"Essai groupe"}  # le volet 8 sert à l'essai 13
TEMPS_MONTEE, TEMPS_DESCENTE = 10.0, 8.0

# Positions prédéfinies de chaque volet : « Soleil » n'a pas le même pourcentage partout, « soleil »
# est écrit en minuscules chez le volet 3, les volets 5 et 7 n'en ont pas.
POSITIONS = {
    1: [("Soleil", 60), ("Chaleur", 33)],
    2: [("Soleil", 60)],
    3: [("soleil", 50)],
    4: [("Chaleur", 30)],
    5: [],
    6: [("Soleil", 60)],
    7: [],
}


def position(entity_id: str):
    return etat(entity_id)["attributes"].get("current_position")


def positions() -> list:
    return [position(v) for v in VOLETS]


def entrees() -> list[dict]:
    return api("GET", "/api/config/config_entries/entry")


def entree_de(titre: str) -> dict | None:
    return next((e for e in entrees() if e["domain"] == "timed_cover" and e["title"] == titre), None)


def nettoyer() -> None:
    """Supprime le groupe d'abord, puis les volets d'essai (jamais d'autres entrées)."""
    for titre in ["Essai groupe"] + sorted(TITRES - {"Essai groupe"}):
        e = entree_de(titre)
        if e:
            api("DELETE", f"/api/config/config_entries/entry/{e['entry_id']}")


def creer_volet(n: int) -> None:
    flux = api("POST", "/api/config/config_entries/flow", {"handler": "timed_cover"})
    flux = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"next_step_id": "entite"})
    flux = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"source_entity": ORIGINES[n - 1]})
    flux = api(
        "POST",
        f"/api/config/config_entries/flow/{flux['flow_id']}",
        {
            "name": f"Essai volet {n}",
            "travel_time_up": TEMPS_MONTEE,
            "travel_time_down": TEMPS_DESCENTE,
            "send_stop_at_ends": False,
            "device_class": "shutter",
            "hide_source": True,
            "take_over": True,
            "source_suffix": "source",
            "positions": {"presets": [{"name": nom, "position": p} for nom, p in POSITIONS[n]]},
        },
    )
    assert flux["type"] == "create_entry", flux


def creer_groupe(nom: str, volets: list[str]) -> dict:
    flux = api("POST", "/api/config/config_entries/flow", {"handler": "timed_cover"})
    flux = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"next_step_id": "groupe"})
    assert flux["step_id"] == "groupe", flux
    return api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"name": nom, "members": volets})


def remettre(valeur: int) -> None:
    for v in VOLETS:
        service("timed_cover", "set_known_position", entity_id=v, position=valeur)
    time.sleep(0.5)


def ordres_recus() -> list[dict]:
    return [o for o in journal() if o["ordre"] in ("open", "close")]


def ecart_ms(ordres: list[dict]) -> float:
    temps = [o["recu"] for o in ordres]
    return (max(temps) - min(temps)) * 1000 if temps else -1.0


def attendre(condition, delai: float) -> float:
    debut = time.monotonic()
    while time.monotonic() - debut < delai:
        if condition():
            return time.monotonic() - debut
        time.sleep(0.25)
    return -1.0


def journal_ha() -> str:
    """Journal de Home Assistant (superviseur), pour y chercher des erreurs."""
    import urllib.request

    requete = urllib.request.Request(base.URL + "/api/hassio/core/logs")
    requete.add_header("Authorization", f"Bearer {base.JETON}")
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return reponse.read().decode(errors="replace")


def essai_desactivation() -> None:
    """Essai 13 : désactiver les autres entités de l'appareil source, puis supprimer l'entité."""
    print("\n13. Désactiver les autres entités de l'appareil source, puis supprimer l'entité")
    huit = "cover.essai_volet_8"
    bouton8 = "button.essai_volet_8_identifier"
    erreurs_avant = journal_ha().count("Error calling entry remove callback")
    flux = api("POST", "/api/config/config_entries/flow", {"handler": "timed_cover"})
    flux = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"next_step_id": "entite"})
    flux = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"source_entity": huit})
    api(
        "POST",
        f"/api/config/config_entries/flow/{flux['flow_id']}",
        {"name": "Essai volet 8", "travel_time_up": TEMPS_MONTEE, "travel_time_down": TEMPS_DESCENTE, "send_stop_at_ends": False, "device_class": "shutter", "hide_source": True, "disable_other_entities": True, "take_over": True, "source_suffix": "source", "positions": {"presets": []}},
    )
    time.sleep(3.0)
    verifier("le bouton « Identifier » de l'appareil source est désactivé", not existe(bouton8), "")
    verifier("le faux volet est renommé « …_source » et masqué", existe("cover.essai_volet_8_source") and modele("{{ is_hidden_entity('cover.essai_volet_8_source') }}") == "True")
    api("DELETE", f"/api/config/config_entries/entry/{entree_de('Essai volet 8')['entry_id']}")
    time.sleep(3.0)
    # Home Assistant recharge l'intégration d'une entité réactivée après un délai d'environ 30 s.
    attente = attendre(lambda: existe(bouton8), 50)
    verifier("le bouton « Identifier » est réactivé (Home Assistant le recharge au bout d'environ 30 s)", attente >= 0, f"{attente:.0f} s")
    verifier("le faux volet retrouve son identifiant, son nom et sa visibilité", existe(huit) and not existe("cover.essai_volet_8_source") and modele(f"{{{{ is_hidden_entity('{huit}') }}}}") == "False", "")
    verifier("aucune erreur de suppression dans le journal", journal_ha().count("Error calling entry remove callback") == erreurs_avant, "")


def main() -> int:
    garder = "--garder" in sys.argv
    if "--desactivation" in sys.argv:  # seulement l'essai 13, sans créer les 7 volets ni le groupe
        nettoyer()
        if not [e for e in entrees() if e["domain"] == "essai_volets"]:
            api("POST", "/api/config/config_entries/flow", {"handler": "essai_volets"})
            time.sleep(2)
        essai_desactivation()
        nettoyer()
        echecs = [r for r in base.resultats if not r[1]]
        print(f"\nRésultat : {len(base.resultats) - len(echecs)}/{len(base.resultats)} vérifications réussies.")
        return 1 if echecs else 0
    print("Préparation : nettoyage, faux volets, volets à temps de trajet...")
    nettoyer()
    if not [e for e in entrees() if e["domain"] == "essai_volets"]:
        api("POST", "/api/config/config_entries/flow", {"handler": "essai_volets"})
        time.sleep(2)
    service("essai_volets", "configurer", delai=1.0)
    for n in range(1, NOMBRE + 1):
        creer_volet(n)
    time.sleep(2)
    remettre(0)

    print("\n1. Création du groupe par le formulaire")
    flux = api("POST", "/api/config/config_entries/flow", {"handler": "timed_cover"})
    verifier("le formulaire commence par un menu", flux["type"] == "menu" and flux["menu_options"] == ["entite", "groupe"], str(flux.get("menu_options")))
    api("DELETE", "/api/config/config_entries/flow/" + flux["flow_id"])
    flux = api("POST", "/api/config/config_entries/flow", {"handler": "timed_cover"})
    flux = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"next_step_id": "groupe"})
    erreur = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"name": "Essai groupe", "members": [VOLETS[0]]})
    verifier("un groupe d'un seul volet est refusé", erreur.get("errors", {}).get("members") == "groupe_trop_petit", str(erreur.get("errors")))
    schema = {c["name"]: c for c in erreur["data_schema"]}
    verifier("la liste des volets ne propose que les entités de l'intégration", schema["members"]["selector"]["entity"].get("integration") == "timed_cover" and schema["members"]["selector"]["entity"].get("multiple") is True, str(schema["members"]["selector"]))
    api("DELETE", "/api/config/config_entries/flow/" + flux["flow_id"])
    resultat = creer_groupe("Essai groupe", VOLETS)
    verifier("le groupe est créé", resultat["type"] == "create_entry", str(resultat.get("type")))
    time.sleep(2.5)
    groupe = etat(GROUPE) if existe(GROUPE) else {"state": "absent", "attributes": {}}
    verifier("cover.essai_groupe existe", groupe["state"] != "absent", groupe["state"])
    verifier("nom affiché = « Essai groupe »", groupe["attributes"].get("friendly_name") == "Essai groupe", str(groupe["attributes"].get("friendly_name")))
    verifier("ouvrir, fermer, arrêter, position (15)", groupe["attributes"].get("supported_features") == 15, str(groupe["attributes"].get("supported_features")))
    verifier("le groupe liste ses 7 volets", sorted(groupe["attributes"].get("members", [])) == sorted(VOLETS), str(groupe["attributes"].get("members")))
    verifier("état supposé, classe « shutter » reprise des volets", groupe["attributes"].get("assumed_state") is True and groupe["attributes"].get("device_class") == "shutter", f"{groupe['attributes'].get('assumed_state')} {groupe['attributes'].get('device_class')}")
    verifier("position de départ = 0, état « closed »", position(GROUPE) == 0 and groupe["state"] == "closed", f"{position(GROUPE)} {groupe['state']}")

    print("\n2. Boutons : un par nom de position, noms comparés sans casse")
    for bouton, nom in (("button.essai_groupe_soleil", "Essai groupe Soleil"), ("button.essai_groupe_chaleur", "Essai groupe Chaleur")):
        verifier(f"{bouton} existe", existe(bouton))
        if existe(bouton):
            verifier(f"nom = « {nom} »", etat(bouton)["attributes"].get("friendly_name") == nom, str(etat(bouton)["attributes"].get("friendly_name")))
    verifier("« soleil » (volet 3) et « Soleil » ne font qu'un seul bouton", not existe("button.essai_groupe_soleil_2"))
    meme_appareil = modele("{{ device_id('cover.essai_groupe') == device_id('button.essai_groupe_soleil') and device_id('cover.essai_groupe') is not none }}")
    verifier("cover et boutons sont sous le même appareil", meme_appareil == "True", meme_appareil)
    autre = modele(f"{{{{ device_id('cover.essai_groupe') != device_id('{VOLETS[0]}') }}}}")
    verifier("l'appareil du groupe est distinct de celui des volets", autre == "True", autre)
    nom_appareil = modele("{{ device_attr(device_id('cover.essai_groupe'), 'name') }}")
    verifier("nom de l'appareil = « Essai groupe »", nom_appareil == "Essai groupe", nom_appareil)

    print("\n3. Fermer : les 7 volets reçoivent l'ordre ensemble, chacun garde sa position")
    depart = [100, 100, 60, 30, 0, 100, 45]
    for v, p in zip(VOLETS, depart):
        service("timed_cover", "set_known_position", entity_id=v, position=p)
    time.sleep(1.0)
    verifier("position du groupe = moyenne des volets (62)", position(GROUPE) == 62, f"{position(GROUPE)}")
    service("essai_volets", "vider")
    debut = time.monotonic()
    service("cover", "close_cover", entity_id=GROUPE)
    duree = time.monotonic() - debut
    recus = ordres_recus()
    verifier("7 ordres reçus", len(recus) == 7, str(len(recus)))
    verifier("écart de réception inférieur à 100 ms", 0 <= ecart_ms(recus) < 100, f"{ecart_ms(recus):.0f} ms")
    verifier("l'appel dure à peu près le délai d'un seul volet (1 s), pas 7 s", duree < 2.0, f"{duree:.2f} s")
    time.sleep(1.0)
    verifier("le groupe est en « closing » pendant le trajet", etat(GROUPE)["state"] == "closing", etat(GROUPE)["state"])
    attendre(lambda: all(e not in ("closing", "opening") for e in [etat(v)["state"] for v in VOLETS]), 14)
    time.sleep(1.0)
    verifier("les 7 volets sont à 0", positions() == [0] * 7, str(positions()))
    verifier("le groupe est « closed » à 0", etat(GROUPE)["state"] == "closed" and position(GROUPE) == 0, f"{etat(GROUPE)['state']} {position(GROUPE)}")

    print("\n4. Aller à 50 % : chacun part de sa position")
    for v, p in zip(VOLETS, depart):
        service("timed_cover", "set_known_position", entity_id=v, position=p)
    service("essai_volets", "vider")
    service("cover", "set_cover_position", entity_id=GROUPE, position=50)
    recus = ordres_recus()
    verifier("7 ordres reçus ensemble", len(recus) == 7 and 0 <= ecart_ms(recus) < 100, f"{len(recus)} ordres, {ecart_ms(recus):.0f} ms")
    sens = sorted((o["volet"], o["ordre"]) for o in recus)
    attendu = sorted((n, "close" if depart[n - 1] > 50 else "open") for n in range(1, 8))
    verifier("chaque volet va dans son sens (fermer s'il est au-dessus de 50, ouvrir sinon)", sens == attendu, str(sens))
    attendre(lambda: all(e not in ("closing", "opening") for e in [etat(v)["state"] for v in VOLETS]), 14)
    time.sleep(1.0)
    verifier("les 7 volets sont à 50", positions() == [50] * 7, str(positions()))
    verifier("le groupe est à 50 et « open »", position(GROUPE) == 50 and etat(GROUPE)["state"] == "open", f"{position(GROUPE)} {etat(GROUPE)['state']}")

    print("\n5. Ouvrir, puis arrêter en cours de route")
    service("essai_volets", "vider")
    service("cover", "open_cover", entity_id=GROUPE)
    time.sleep(3.0)
    service("essai_volets", "vider")
    service("cover", "stop_cover", entity_id=GROUPE)
    arrets = [o for o in journal() if o["ordre"] == "stop"]
    verifier("7 ordres d'arrêt, reçus ensemble", len(arrets) == 7 and ecart_ms(arrets) < 100, f"{len(arrets)} ordres, {ecart_ms(arrets):.0f} ms")
    p1 = positions()
    time.sleep(2.0)
    verifier("les volets restent figés après l'arrêt", positions() == p1 and 50 < min(p1) and max(p1) < 100, str(p1))
    verifier("le groupe n'est plus en mouvement", etat(GROUPE)["state"] == "open", etat(GROUPE)["state"])

    print("\n6. Boutons de position : chaque volet va à son propre pourcentage")
    remettre(0)
    service("essai_volets", "vider")
    service("button", "press", entity_id="button.essai_groupe_soleil")
    recus = ordres_recus()
    verifier("seuls les 4 volets qui ont « Soleil » reçoivent l'ordre", sorted(o["volet"] for o in recus) == [1, 2, 3, 6], str(sorted(o["volet"] for o in recus)))
    verifier("ordres reçus ensemble", 0 <= ecart_ms(recus) < 100, f"{ecart_ms(recus):.0f} ms")
    attendre(lambda: all(e not in ("closing", "opening") for e in [etat(v)["state"] for v in VOLETS]), 14)
    time.sleep(1.0)
    verifier("positions : 60, 60, 50, 0, 0, 60, 0 (le volet 3 a 50 %)", positions() == [60, 60, 50, 0, 0, 60, 0], str(positions()))
    service("essai_volets", "vider")
    service("button", "press", entity_id="button.essai_groupe_chaleur")
    verifier("« Chaleur » : seuls les volets 1 et 4 reçoivent l'ordre", sorted(o["volet"] for o in ordres_recus()) == [1, 4], str(sorted(o["volet"] for o in ordres_recus())))
    attendre(lambda: all(e not in ("closing", "opening") for e in [etat(v)["state"] for v in VOLETS]), 14)
    time.sleep(1.0)
    verifier("positions : 33, 60, 50, 30, 0, 60, 0", positions() == [33, 60, 50, 30, 0, 60, 0], str(positions()))

    print("\n7. Recalage de tous les volets par le service du groupe")
    service("timed_cover", "set_known_position", entity_id=GROUPE, position=70)
    time.sleep(1.0)
    verifier("les 7 volets sont recalés à 70, sans mouvement", positions() == [70] * 7 and etat(GROUPE)["state"] == "open", str(positions()))

    print("\n8. Un volet indisponible est ignoré")
    source3 = "cover.essai_volet_3_source"
    ancien = etat(source3)
    api("POST", f"/api/states/{source3}", {"state": "unavailable", "attributes": ancien["attributes"]})
    time.sleep(1.0)
    verifier("le volet 3 est indisponible, le groupe reste disponible", etat(VOLETS[2])["state"] == "unavailable" and etat(GROUPE)["state"] != "unavailable", f"{etat(VOLETS[2])['state']} / {etat(GROUPE)['state']}")
    service("essai_volets", "vider")
    service("cover", "close_cover", entity_id=GROUPE)
    recus = ordres_recus()
    verifier("les 6 autres volets reçoivent l'ordre", sorted(o["volet"] for o in recus) == [1, 2, 4, 5, 6, 7], str(sorted(o["volet"] for o in recus)))
    attendre(lambda: all(etat(v)["state"] not in ("closing", "opening") for v in VOLETS if v != VOLETS[2]), 14)
    time.sleep(1.0)
    verifier("la position du groupe ignore le volet indisponible", position(GROUPE) == 0, f"{position(GROUPE)}")
    api("POST", f"/api/states/{source3}", {"state": ancien["state"], "attributes": ancien["attributes"]})
    time.sleep(1.0)
    verifier("le volet 3 redevient disponible", etat(VOLETS[2])["state"] != "unavailable", etat(VOLETS[2])["state"])

    print("\n9. Une position ajoutée à un volet crée le bouton du groupe")
    entree7 = entree_de("Essai volet 7")
    flux = api("POST", "/api/config/config_entries/options/flow", {"handler": entree7["entry_id"]})
    api(
        "POST",
        f"/api/config/config_entries/options/flow/{flux['flow_id']}",
        {"travel_time_up": TEMPS_MONTEE, "travel_time_down": TEMPS_DESCENTE, "send_stop_at_ends": False, "device_class": "shutter", "hide_source": True, "disable_other_entities": False, "positions": {"presets": [{"name": "Nuit", "position": 10}]}},
    )
    time.sleep(4.0)
    verifier("button.essai_groupe_nuit apparaît", existe("button.essai_groupe_nuit"))
    verifier("les boutons existants sont conservés", existe("button.essai_groupe_soleil") and existe("button.essai_groupe_chaleur"))

    print("\n10. Modifier les volets du groupe (options)")
    entree_groupe = entree_de("Essai groupe")
    flux = api("POST", "/api/config/config_entries/options/flow", {"handler": entree_groupe["entry_id"]})
    verifier("les options d'un groupe sont la liste de ses volets", flux.get("step_id") == "groupe" and [c["name"] for c in flux["data_schema"]] == ["members"], f"{flux.get('step_id')} {[c['name'] for c in flux.get('data_schema', [])]}")
    api("POST", f"/api/config/config_entries/options/flow/{flux['flow_id']}", {"members": VOLETS[:6]})
    time.sleep(3.0)
    verifier("le groupe n'a plus que 6 volets", sorted(etat(GROUPE)["attributes"].get("members", [])) == sorted(VOLETS[:6]), str(etat(GROUPE)["attributes"].get("members")))
    verifier("le bouton « Nuit » (volet 7 seul) disparaît", not existe("button.essai_groupe_nuit"))
    flux = api("POST", "/api/config/config_entries/options/flow", {"handler": entree_groupe["entry_id"]})
    api("POST", f"/api/config/config_entries/options/flow/{flux['flow_id']}", {"members": VOLETS})
    time.sleep(3.0)
    verifier("les 7 volets sont de nouveau dans le groupe", len(etat(GROUPE)["attributes"].get("members", [])) == 7)

    print("\n11. Diagnostic du groupe")
    try:
        diag = api("GET", f"/api/diagnostics/config_entry/{entree_groupe['entry_id']}")
        donnees = diag.get("data", diag)
        verifier("le diagnostic liste le groupe, ses volets et ses boutons", len(donnees.get("members", [])) == 7 and len(donnees.get("preset_buttons", [])) >= 2 and donnees.get("cover", {}).get("state"), f"{len(donnees.get('members', []))} volets, {len(donnees.get('preset_buttons', []))} boutons")
    except RuntimeError as erreur:
        verifier("le diagnostic est téléchargeable", False, str(erreur)[:120])

    print("\n12. Supprimer un volet le retire du groupe ; supprimer le groupe ne touche pas aux volets")
    api("DELETE", f"/api/config/config_entries/entry/{entree7['entry_id']}")
    time.sleep(3.0)
    verifier("le groupe n'a plus que 6 volets", len(etat(GROUPE)["attributes"].get("members", [])) == 6, str(etat(GROUPE)["attributes"].get("members")))
    api("DELETE", f"/api/config/config_entries/entry/{entree_groupe['entry_id']}")
    time.sleep(2.5)
    verifier("l'entité cover et les boutons du groupe disparaissent", not existe(GROUPE) and not existe("button.essai_groupe_soleil"))
    appareil = modele("{{ device_id('cover.essai_groupe') }}")
    verifier("l'appareil du groupe disparaît", appareil in ("None", ""), appareil)
    verifier("les volets sont intacts", all(existe(v) and etat(v)["state"] != "unavailable" for v in VOLETS[:6]), str([etat(v)["state"] for v in VOLETS[:6]]))

    essai_desactivation()

    if not garder:
        print("\nNettoyage...")
        nettoyer()
        time.sleep(2)
        verifier("les faux volets retrouvent leurs identifiants", all(existe(o) and "travel_time_up" not in etat(o)["attributes"] for o in ORIGINES), "")

    echecs = [r for r in base.resultats if not r[1]]
    print(f"\nRésultat : {len(base.resultats) - len(echecs)}/{len(base.resultats)} vérifications réussies.")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
