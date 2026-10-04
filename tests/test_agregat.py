"""Tests des calculs d'un groupe de volets (sans Home Assistant).

Lancer depuis la racine du dépôt :  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_CHEMIN = (
    Path(__file__).resolve().parents[1] / "custom_components" / "timed_cover" / "agregat.py"
)
_spec = importlib.util.spec_from_file_location("agregat", _CHEMIN)
agregat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agregat)


class TestCleNom(unittest.TestCase):
    def test_casse_accents_et_ponctuation_ignores(self):
        self.assertEqual(agregat.cle_nom("Soleil"), agregat.cle_nom("  soleil "))
        self.assertEqual(agregat.cle_nom("Pare-soleil"), agregat.cle_nom("pare soleil"))
        self.assertEqual(agregat.cle_nom("Été"), "ete")

    def test_nom_vide_ou_sans_lettre(self):
        self.assertEqual(agregat.cle_nom("  -- "), "")


class TestPositionMoyenne(unittest.TestCase):
    def test_moyenne_de_volets_a_des_positions_differentes(self):
        self.assertEqual(agregat.position_moyenne([100, 0, 40]), 47)

    def test_ignore_les_positions_inconnues(self):
        self.assertEqual(agregat.position_moyenne([None, 60, None, 40]), 50)

    def test_aucune_position_connue(self):
        self.assertIsNone(agregat.position_moyenne([None, None]))
        self.assertIsNone(agregat.position_moyenne([]))

    def test_arrondi_a_la_valeur_superieure_sur_la_demie(self):
        self.assertEqual(agregat.position_moyenne([0, 1]), 1)


class TestEtatGroupe(unittest.TestCase):
    def test_tous_fermes(self):
        self.assertEqual(agregat.etat_groupe(["closed", "closed"]), (False, False, True))

    def test_un_seul_ouvert_suffit_pour_ne_pas_etre_ferme(self):
        self.assertEqual(agregat.etat_groupe(["closed", "open"]), (False, False, False))

    def test_mouvement_des_qu_un_volet_bouge(self):
        self.assertEqual(agregat.etat_groupe(["closed", "opening"]), (True, False, False))
        self.assertEqual(agregat.etat_groupe(["open", "closing"]), (False, True, False))

    def test_sans_volet_disponible_l_etat_est_inconnu(self):
        self.assertEqual(agregat.etat_groupe([]), (False, False, None))


class TestRegrouperPositions(unittest.TestCase):
    def test_union_par_nom_avec_pourcentage_propre_a_chaque_volet(self):
        reunies = agregat.regrouper_positions(
            {
                "a": [{"name": "Soleil", "position": 60}, {"name": "Chaleur", "position": 33}],
                "b": [{"name": "soleil", "position": 50, "icon": "mdi:weather-sunny"}],
                "c": [{"name": "Chaleur", "position": 30}],
                "d": [],
            }
        )
        self.assertEqual(set(reunies), {"soleil", "chaleur"})
        self.assertEqual(reunies["soleil"]["volets"], {"a": 60, "b": 50})
        self.assertEqual(reunies["chaleur"]["volets"], {"a": 33, "c": 30})

    def test_nom_affiche_du_premier_volet_et_premiere_icone_trouvee(self):
        reunies = agregat.regrouper_positions(
            {
                "a": [{"name": "Soleil", "position": 60}],
                "b": [{"name": "soleil", "position": 50, "icon": "mdi:weather-sunny"}],
            }
        )
        self.assertEqual(reunies["soleil"]["nom"], "Soleil")
        self.assertEqual(reunies["soleil"]["icone"], "mdi:weather-sunny")

    def test_aucun_volet_aucune_position(self):
        self.assertEqual(agregat.regrouper_positions({}), {})


if __name__ == "__main__":
    unittest.main()
