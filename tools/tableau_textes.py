#!/usr/bin/env python3
"""Génère le tableau de relecture des textes (anglais / français) à partir des fichiers de traduction.

Usage : python3 tools/tableau_textes.py [chemin_du_fichier_markdown_à_écrire]

Le tableau est tiré de `strings.json` (anglais) et `translations/fr.json` : il ne peut donc pas
diverger des textes réellement affichés. Une référence (Z3.7, par exemple) identifie chaque ligne
pour qu'une correction puisse la citer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent.parent / "custom_components" / "timed_cover"
EN = json.loads((DOSSIER / "strings.json").read_text())
FR = json.loads((DOSSIER / "translations" / "fr.json").read_text())


def chemin(source: dict, *cles: str) -> str:
    for cle in cles:
        source = source[cle]
    return source


# Noms lisibles des champs et des erreurs (les noms internes ne parlent à personne).
NOMS_CHAMPS = {
    "source_entity": "Entité à sélectionner", "name": "Nom", "travel_time_up": "Délai d'ouverture",
    "travel_time_down": "Délai de fermeture", "send_stop_at_ends": "Stop aux extrémités",
    "device_class": "Classe d'appareil", "hide_source": "Masquer l'entité source",
    "disable_other_entities": "Désactiver les autres entités", "take_over": "Reprendre le nom",
    "source_suffix": "Suffixe", "position": "Position", "icon": "Icône",
    "members": "Entités du groupe",
}
NOMS_ERREURS = {
    "source_introuvable": "Ouvrant introuvable", "source_deja_chronometree": "Ouvrant déjà lié",
    "suffixe_invalide": "Suffixe invalide", "positions_invalides": "Position invalide",
    "noms_en_double": "Noms en double", "trop_de_positions": "Trop de positions",
    "groupe_trop_petit": "Groupe trop petit", "volet_invalide": "Entité refusée",
    "nom_invalide": "Nom invalide",
}
VUS: dict[tuple[str, str], str] = {}  # (anglais, français) -> référence de la première apparition


def cellule(texte: str) -> str:
    return str(texte).replace("|", "\\|").replace("\n", " ")


class Zone:
    def __init__(self, numero: int, titre: str, ou: str) -> None:
        self.numero, self.titre, self.ou, self.lignes, self.chemins = numero, titre, ou, [], []

    def ajouter(self, intitule: str, *cles: str) -> None:
        self.lignes.append((intitule, chemin(EN, *cles), chemin(FR, *cles)))
        self.chemins.append(cles)

    def champs(self, base: tuple[str, ...], noms: list[str]) -> None:
        for nom in noms:
            self.ajouter(f"Champ « {NOMS_CHAMPS[nom]} » : libellé", *base, "data", nom)
            self.ajouter(f"Champ « {NOMS_CHAMPS[nom]} » : aide", *base, "data_description", nom)

    def bloc_positions(self, base: tuple[str, ...]) -> None:
        self.ajouter("Bloc des positions : titre", *base, "sections", "positions", "name")
        self.ajouter("Bloc des positions : explication", *base, "sections", "positions", "description")
        self.ajouter("Liste des positions : libellé", *base, "sections", "positions", "data", "presets")

    def markdown(self) -> str:
        sortie = [f"## Zone {self.numero} — {self.titre}", "", f"*Où : {self.ou}*", "",
                  "| Réf. | Élément | Anglais | Français |", "| --- | --- | --- | --- |"]
        for i, (intitule, en, fr) in enumerate(self.lignes, start=1):
            ref = f"Z{self.numero}.{i}"
            premiere = VUS.get((en, fr))
            if premiere and len(en) > 20:  # texte identique à un autre : inutile de le relire deux fois
                en = fr = f"*identique à {premiere}*"
            else:
                VUS.setdefault((en, fr), ref)
            sortie.append(f"| {ref} | {cellule(intitule)} | {cellule(en)} | {cellule(fr)} |")
        return "\n".join(sortie) + "\n"


def construire() -> list[Zone]:
    zones = []
    z = Zone(1, "Bouton d'ajout", "page de l'intégration, bouton pour créer une nouvelle entité")
    z.ajouter("Bouton", "config", "initiate_flow", "user"); zones.append(z)

    z = Zone(2, "Création, étape 1 : choisir l'entité source", "première fenêtre quand on ajoute une entité")
    base = ("config", "step", "entite")
    z.ajouter("Titre", *base, "title"); z.ajouter("Description", *base, "description")
    z.champs(base, ["source_entity"]); zones.append(z)

    z = Zone(3, "Création, étape 2 : réglages de l'entité", "deuxième fenêtre, dans l'ordre d'affichage")
    base = ("config", "step", "parametres")
    z.ajouter("Titre", *base, "title"); z.ajouter("Description ({source} = ouvrant choisi)", *base, "description")
    z.champs(base, ["name", "travel_time_up", "travel_time_down", "send_stop_at_ends", "device_class",
                    "hide_source", "disable_other_entities"])
    z.bloc_positions(base)
    z.champs(base, ["take_over", "source_suffix"]); zones.append(z)

    z = Zone(4, "Création : messages d'erreur", "affichés sous le formulaire quand une saisie est refusée")
    for cle in ("source_introuvable", "source_deja_chronometree", "suffixe_invalide",
                "positions_invalides", "noms_en_double", "trop_de_positions"):
        z.ajouter(f"Erreur « {NOMS_ERREURS[cle]} »", "config", "error", cle)
    z.ajouter("Abandon « déjà configuré »", "config", "abort", "already_configured"); zones.append(z)

    z = Zone(5, "Réglages de l'entité (roue dentée)", "formulaire de modification d'une entité existante")
    base = ("options", "step", "init")
    z.ajouter("Titre", *base, "title"); z.ajouter("Description", *base, "description")
    z.champs(base, ["travel_time_up", "travel_time_down", "send_stop_at_ends", "device_class",
                    "hide_source", "disable_other_entities"])
    z.bloc_positions(base)
    for cle in ("positions_invalides", "noms_en_double", "trop_de_positions"):
        z.ajouter(f"Erreur « {NOMS_ERREURS[cle]} »", "options", "error", cle)
    zones.append(z)

    z = Zone(6, "Classes d'appareil", "liste déroulante « Classe d'appareil » (mots de Home Assistant)")
    for cle in EN["selector"]["device_class"]["options"]:
        z.ajouter(f"Option « {cle} »", "selector", "device_class", "options", cle)
    zones.append(z)

    z = Zone(7, "Ligne d'une position prédéfinie", "fenêtre « Ajouter » / crayon d'une ligne de la liste")
    for champ in ("name", "position", "icon"):
        z.ajouter(f"Champ « {NOMS_CHAMPS[champ] if champ != 'name' else 'Nom du bouton'} » : libellé", "selector", "presets", "fields", champ, "name")
        z.ajouter(f"Champ « {NOMS_CHAMPS[champ] if champ != 'name' else 'Nom du bouton'} » : aide", "selector", "presets", "fields", champ, "description")
    zones.append(z)

    z = Zone(8, "Service « Recaler la position »", "Outils de développement, scripts et automatisations")
    base = ("services", "set_known_position")
    z.ajouter("Nom du service", *base, "name"); z.ajouter("Description", *base, "description")
    z.ajouter("Champ « position » : nom", *base, "fields", "position", "name")
    z.ajouter("Champ « position » : aide", *base, "fields", "position", "description")
    zones.append(z)
    return zones


def zone_code() -> str:
    """Zone 9 : messages d'erreur du code (traduisibles) et formats écrits par l'intégration."""
    def ligne(ref, ou, en, fr):
        return f"| {ref} | {cellule(ou)} | {cellule(en)} | {cellule(fr)} |"
    exceptions = ("exceptions",)
    rows = [
        ligne("Z9.1", "Message d'erreur quand on commande une entité dont l'entité source est indisponible",
              chemin(EN, *exceptions, "source_unavailable", "message"), chemin(FR, *exceptions, "source_unavailable", "message")),
        ligne("Z9.2", "Message d'erreur quand on appuie sur un bouton de position dont l'entité personnalisée a disparu",
              chemin(EN, *exceptions, "cover_not_found", "message"), chemin(FR, *exceptions, "cover_not_found", "message")),
        ligne("Z9.3", "Suffixe proposé pour l'entité source (valeur du champ)", "source", "source"),
        ligne("Z9.4", "Nom de l'entité source une fois renommée", "<name> (<suffix>), for example Kitchen Shutter (source)",
              "<Nom> (<suffixe>), par exemple Volet Cuisine (source)"),
        ligne("Z9.5", "Nom d'un bouton de position", "<cover name> <position name>, for example Kitchen Shutter Sun",
              "<Nom de l'entité> <Nom de la position>, par exemple Volet Cuisine Soleil"),
        ligne("Z9.6", "Titre de l'intégration (carte, recherche)", "Custom Cover Position", "Custom Cover Position"),
    ]
    return ("## Zone 9 — Textes écrits dans le code\n\n*Messages d'erreur (anglais par défaut, avec traduction) et formats construits "
            "par l'intégration.*\n\n| Réf. | Où il apparaît | Anglais | Français |\n| --- | --- | --- | --- |\n" + "\n".join(rows) + "\n")


def zones_groupes() -> list[Zone]:
    """Zones 10 à 12 : les groupes de volets (ajoutées après la zone 9 pour garder la numérotation)."""
    zones = []
    z = Zone(10, "Menu de départ et création d'un groupe", "premières fenêtres quand on ajoute une entité ou un groupe")
    base = ("config", "step", "user")
    z.ajouter("Menu : titre", *base, "title"); z.ajouter("Menu : explication", *base, "description")
    z.ajouter("Menu : choix « entité »", *base, "menu_options", "entite")
    z.ajouter("Menu : choix « groupe »", *base, "menu_options", "groupe")
    base = ("config", "step", "groupe")
    z.ajouter("Création du groupe : titre", *base, "title"); z.ajouter("Création du groupe : explication", *base, "description")
    z.champs(base, ["name", "members"])
    for cle in ("groupe_trop_petit", "volet_invalide", "nom_invalide"):
        z.ajouter(f"Erreur « {NOMS_ERREURS[cle]} »", "config", "error", cle)
    zones.append(z)

    z = Zone(11, "Réglages d'un groupe (roue dentée)", "formulaire de modification d'un groupe existant")
    base = ("options", "step", "groupe")
    z.ajouter("Titre", *base, "title"); z.ajouter("Description", *base, "description")
    z.champs(base, ["members"])
    for cle in ("groupe_trop_petit", "volet_invalide"):
        z.ajouter(f"Erreur « {NOMS_ERREURS[cle]} »", "options", "error", cle)
    zones.append(z)

    z = Zone(12, "Groupes : textes écrits dans le code", "messages d'erreur d'un groupe et appareil du groupe")
    z.ajouter("Erreur quand aucune entité du groupe n'est disponible ({name} = groupe)", "exceptions", "group_no_member", "message")
    z.ajouter("Erreur quand l'ordre échoue pour certaines entités ({members}, {error})", "exceptions", "group_members_failed", "message")
    zones.append(z)
    return zones


def main() -> None:
    zones = construire()
    groupes = zones_groupes()
    total = sum(len(z.lignes) for z in zones + groupes)
    entete = (
        "# Relecture des textes — Custom Cover Position\n\n"
        "Chaque ligne a une référence (Z3.7, par exemple) : pour corriger, cite la référence et le texte voulu. "
        "Les colonnes anglais et français sont tirées des fichiers de traduction ; ce tableau ne peut donc pas "
        "différer de ce qui s'affiche. Les mots entre accolades, comme `{source}`, sont remplacés par Home Assistant.\n\n"
        f"{total} lignes dans les zones 1 à 8 et 10 à 12 (les textes identiques à un texte déjà présenté sont signalés « identique à… » : "
        "inutile de les relire), plus 6 textes de la zone 9.\n\n"
    )
    contenu = (entete + "\n".join(z.markdown() for z in zones) + "\n" + zone_code()
               + "\n" + "\n".join(z.markdown() for z in groupes))
    cible = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("relecture-textes.md")
    cible.write_text(contenu)
    print(f"{cible} : {total} textes dans {len(zones) + len(groupes)} zones, plus la zone 9.")


if __name__ == "__main__":
    main()
