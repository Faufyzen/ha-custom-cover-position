#!/usr/bin/env python3
"""Reproduit, dans la VM ha-sandbox, la commande de plusieurs volets à temps de trajet d'un coup.

Compare plusieurs façons de commander 7 volets (faux volets `essai_volets`, avec un délai
d'acceptation réglable, comme l'envoi d'une commande à Overkiz) :
  liste      un appel de service avec la liste des volets (ce que fait le groupe natif en interne) ;
  sequence   un script qui appelle les volets l'un après l'autre (ce que fait une cover template) ;
  parallele  un script dont les appels sont dans une action `parallel:` ;
  gabarit    une vraie cover template « groupe » dont les actions appellent les volets l'un après l'autre ;
  natif      un groupe natif de covers (assistant « Groupe »).

Pour chaque essai : durée de l'appel, instants où chaque faux volet REÇOIT l'ordre (le journal
tient l'horloge de la VM), écart entre le premier et le dernier, ordres perdus, position finale de
chaque volet et trajectoires anormales (une position qui recule pendant que le volet avance).

Prérequis : jeton dans ~/.ha-sandbox-token (jamais affiché), intégrations timed_cover et
essai_volets déployées dans la sandbox (rsync de tools/essai_volets/ vers
/Volumes/config/custom_components/essai_volets/, puis redémarrage). Ne touche qu'aux entrées
« Essai volet N », « Essai gabarit », « Essai groupe natif » et aux scripts `essai_*` : jamais aux
vrais volets (Overkiz) de la sandbox, qui sont reliés au compte cloud de Sophie.

Usage : python3 tools/essai_parallele.py [--delai 1.0] [--methodes liste,sequence,...] [--garder]
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from essai_sandbox import api, etat, service  # noqa: E402  (outils communs : jeton, appels API)

NOMBRE = 7
IDS = [f"cover.essai_volet_{n}" for n in range(1, NOMBRE + 1)]  # nouveaux volets, après l'échange des noms
ORIGINES = list(IDS)  # avant l'échange : ce sont les faux volets
TITRES = {f"Essai volet {n}" for n in range(1, NOMBRE + 1)} | {"Essai gabarit", "Essai groupe natif"}
SCRIPTS = [f"essai_{m}_{o}" for m in ("seq", "par") for o in ("close", "open", "pos50")]
TEMPS_MONTEE, TEMPS_DESCENTE = 10.0, 8.0

# Positions de départ : des volets en partie ouverts, comme le soir.
DEPART_FERMER = [100, 100, 60, 30, 0, 100, 45]
DEPART_OUVRIR = [0, 0, 40, 70, 100, 0, 55]
SCENARIOS = {
    "fermer": ("close", 0, DEPART_FERMER),
    "ouvrir": ("open", 100, DEPART_OUVRIR),
    "50 %": ("pos50", 50, DEPART_FERMER),
}


def entrees(domaine: str) -> list[dict]:
    return [e for e in api("GET", "/api/config/config_entries/entry") if e["domain"] == domaine]


def nettoyer(tout: bool = False) -> None:
    for e in api("GET", "/api/config/config_entries/entry"):
        if e["domain"] in ("timed_cover", "template", "group") and e["title"] in TITRES:
            api("DELETE", f"/api/config/config_entries/entry/{e['entry_id']}")
    for s in SCRIPTS:
        try:
            api("DELETE", f"/api/config/script/config/{s}")
        except RuntimeError:
            pass
    if tout:
        for e in entrees("essai_volets"):
            api("DELETE", f"/api/config/config_entries/entry/{e['entry_id']}")


def creer_timed(n: int) -> None:
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
        },
    )
    assert flux["type"] == "create_entry", flux


def appels(service_nom: str, extra: dict | None = None) -> list[dict]:
    return [{"action": service_nom, "target": {"entity_id": i}, **({"data": extra} if extra else {})} for i in IDS]


def creer_scripts() -> None:
    for ordre, nom_service, extra in (
        ("close", "cover.close_cover", None),
        ("open", "cover.open_cover", None),
        ("pos50", "cover.set_cover_position", {"position": 50}),
    ):
        api("POST", f"/api/config/script/config/essai_seq_{ordre}", {"alias": f"Essai séquence {ordre}", "sequence": appels(nom_service, extra)})
        api("POST", f"/api/config/script/config/essai_par_{ordre}", {"alias": f"Essai parallèle {ordre}", "sequence": [{"parallel": appels(nom_service, extra)}]})


def _flux_helper(domaine: str, donnees: dict) -> None:
    flux = api("POST", "/api/config/config_entries/flow", {"handler": domaine})
    flux = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", {"next_step_id": "cover"})
    flux = api("POST", f"/api/config/config_entries/flow/{flux['flow_id']}", donnees)
    assert flux["type"] == "create_entry", flux


def creer_helpers() -> None:
    liste = str(IDS)
    positions = f"{{% set p = {liste} | map('state_attr', 'current_position') | map('int', 0) | list %}}"
    _flux_helper(
        "template",
        {
            "name": "Essai gabarit",
            "state": positions + "{{ 'open' if p | sum > 0 else 'closed' }}",
            "position": positions + "{{ (p | sum / p | length) | round(0) | int }}",
            "open_cover": appels("cover.open_cover"),
            "close_cover": appels("cover.close_cover"),
            "stop_cover": appels("cover.stop_cover"),
            "set_cover_position": appels("cover.set_cover_position", {"position": "{{ position }}"}),
        },
    )
    _flux_helper("group", {"name": "Essai groupe natif", "entities": IDS, "hide_members": False})


def remettre(positions: list[int]) -> None:
    for entite, p in zip(IDS, positions):
        service("timed_cover", "set_known_position", entity_id=entite, position=p)
    time.sleep(0.5)


def journal() -> list[dict]:
    return api("POST", "/api/services/essai_volets/journal?return_response", {})["service_response"]["ordres"]


class Releve(threading.Thread):
    """Relève la position et l'état de chaque volet (et d'une entité de groupe) toutes les 0,3 s."""

    def __init__(self, extra: str | None) -> None:
        super().__init__(daemon=True)
        self.extra, self.points, self.arret = extra, [], False

    def run(self) -> None:
        while not self.arret:
            t = time.monotonic()
            try:
                tous = {s["entity_id"]: s for s in api("GET", "/api/states")}
            except RuntimeError:
                continue
            ligne = {
                "t": t,
                "pos": [tous[i]["attributes"].get("current_position") for i in IDS],
                "etat": [tous[i]["state"] for i in IDS],
            }
            if self.extra:
                ligne["extra"] = (tous[self.extra]["state"], tous[self.extra]["attributes"].get("current_position"))
            self.points.append(ligne)
            time.sleep(max(0.0, 0.3 - (time.monotonic() - t)))


def lancer(methode: str, ordre: str) -> str | None:
    """Envoie l'ordre selon la méthode ; renvoie l'entité de groupe à relever, s'il y en a une."""
    nom_service = {"close": "close_cover", "open": "open_cover", "pos50": "set_cover_position"}[ordre]
    extra = {"position": 50} if ordre == "pos50" else {}
    if methode == "liste":
        service("cover", nom_service, entity_id=IDS, **extra)
    elif methode == "sequence":
        service("script", f"essai_seq_{ordre}")
    elif methode == "parallele":
        service("script", f"essai_par_{ordre}")
    elif methode == "gabarit":
        service("cover", nom_service, entity_id="cover.essai_gabarit", **extra)
        return "cover.essai_gabarit"
    elif methode == "natif":
        service("cover", nom_service, entity_id="cover.essai_groupe_natif", **extra)
        return "cover.essai_groupe_natif"
    return None


def anomalies(trajectoire: list[int | None], cible: int) -> list[str]:
    """Positions qui reculent alors que le volet va vers sa cible (ex. 100, puis 0, puis ça remonte)."""
    remarques = []
    precedent = None
    for p in trajectoire:
        if p is None:
            continue
        if precedent is not None and p != precedent and precedent != cible:
            vers_la_cible = (p > precedent) == (cible > precedent)
            if not vers_la_cible:
                remarques.append(f"{precedent}→{p}")
        precedent = p
    return remarques


def essai(methode: str, nom: str, ordre: str, cible: int, depart: list[int]) -> dict:
    remettre(depart)
    service("essai_volets", "vider")
    # Une cover template relève sa position seule : on laisse le temps à son état de se mettre à jour.
    time.sleep(1.0)
    releve = Releve("cover.essai_gabarit" if methode == "gabarit" else "cover.essai_groupe_natif" if methode == "natif" else None)
    releve.start()
    debut = time.monotonic()
    lancer(methode, ordre)
    duree_appel = time.monotonic() - debut
    # Attente de la fin des mouvements (10 s au plus après le retour de l'appel, plus la marge).
    limite = time.monotonic() + 16
    while time.monotonic() < limite:
        time.sleep(0.5)
        derniers = releve.points[-1]["etat"] if releve.points else []
        if derniers and all(e not in ("opening", "closing") for e in derniers) and time.monotonic() - debut > duree_appel + 1.5:
            break
    releve.arret = True
    releve.join()
    ordres = [o for o in journal() if o["ordre"] in ("open", "close")]
    recus = {o["volet"]: o["recu"] for o in ordres}
    accep = [o.get("accepte") for o in ordres if o.get("accepte")]
    premier = min(recus.values()) if recus else None
    finales = releve.points[-1]["pos"]
    return {
        "methode": methode,
        "scenario": nom,
        "duree_appel": duree_appel,
        "recus": len(recus),
        "ecart_recu_ms": (max(recus.values()) - premier) * 1000 if recus else None,
        "ecart_accepte_ms": (max(accep) - min(accep)) * 1000 if accep else None,
        "decalages_ms": {v: round((t - premier) * 1000) for v, t in sorted(recus.items())},
        "finales": finales,
        "cible": cible,
        "pas_a_la_cible": [i + 1 for i, p in enumerate(finales) if p is None or abs(p - cible) > 1],
        "anomalies": {i + 1: a for i in range(NOMBRE) if (a := anomalies([pt["pos"][i] for pt in releve.points], cible))},
        "extra": [pt["extra"] for pt in releve.points if "extra" in pt][-1:] or None,
    }


def afficher(r: dict) -> None:
    ecart = f"{r['ecart_recu_ms']:.0f} ms" if r["ecart_recu_ms"] is not None else "—"
    print(
        f"  {r['methode']:<9} {r['scenario']:<7} appel {r['duree_appel']:5.2f} s | ordres reçus {r['recus']}/{NOMBRE} | "
        f"écart de réception {ecart:>8} | position finale {r['finales']} (cible {r['cible']})"
    )
    if r["pas_a_la_cible"]:
        print(f"      ⚠ volets pas à la cible : {r['pas_a_la_cible']}")
    if r["anomalies"]:
        print(f"      ⚠ trajectoires anormales : {r['anomalies']}")
    if r["extra"]:
        print(f"      entité de groupe en fin d'essai : {r['extra'][0]}")


def main() -> int:
    garder = "--garder" in sys.argv
    delai = float(sys.argv[sys.argv.index("--delai") + 1]) if "--delai" in sys.argv else 1.0
    methodes = sys.argv[sys.argv.index("--methodes") + 1].split(",") if "--methodes" in sys.argv else ["liste", "sequence", "parallele", "gabarit", "natif"]

    print("Préparation : nettoyage, faux volets, volets à temps de trajet, scripts, groupes...")
    nettoyer()
    if not entrees("essai_volets"):
        api("POST", "/api/config/config_entries/flow", {"handler": "essai_volets"})
        time.sleep(2)
    service("essai_volets", "configurer", delai=delai)
    for n in range(1, NOMBRE + 1):
        creer_timed(n)
    time.sleep(2)
    creer_scripts()
    if {"gabarit", "natif"} & set(methodes):
        creer_helpers()
    time.sleep(2)
    print(f"Délai d'acceptation de chaque faux volet : {delai} s. {NOMBRE} volets, montée {TEMPS_MONTEE} s, descente {TEMPS_DESCENTE} s.\n")

    tous = []
    try:
        for methode in methodes:
            print(f"Méthode « {methode} »")
            for nom, (ordre, cible, depart) in SCENARIOS.items():
                r = essai(methode, nom, ordre, cible, depart)
                afficher(r)
                tous.append(r)
            print()
    finally:
        if not garder:
            print("Nettoyage...")
            nettoyer()
    print("Décalages de réception par volet (ms depuis le premier), scénario « fermer » :")
    for r in tous:
        if r["scenario"] == "fermer":
            print(f"  {r['methode']:<9} {r['decalages_ms']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
