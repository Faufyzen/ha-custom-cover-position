"""Tests de l'estimateur de position (sans Home Assistant).

Lancer depuis la racine du dépôt :  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

# On charge travel.py directement : importer le paquet `timed_cover` demanderait Home Assistant.
_CHEMIN = (
    Path(__file__).resolve().parents[1] / "custom_components" / "timed_cover" / "travel.py"
)
_spec = importlib.util.spec_from_file_location("travel", _CHEMIN)
travel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(travel)

Direction = travel.Direction
TravelEstimator = travel.TravelEstimator


class TestTravelEstimator(unittest.TestCase):
    """Comportement de TravelEstimator."""

    def setUp(self) -> None:
        # Montée en 40 s, descente en 20 s : les deux sens sont volontairement différents.
        self.e = TravelEstimator(temps_montee=40, temps_descente=20, position=0)

    def test_immobile_au_depart(self) -> None:
        self.assertEqual(self.e.position(100.0), 0.0)
        self.assertFalse(self.e.en_mouvement)
        self.assertIs(self.e.sens, Direction.ARRET)

    def test_ouverture_proportionnelle_au_temps(self) -> None:
        duree = self.e.demarrer(100, maintenant=1000.0)
        self.assertAlmostEqual(duree, 40.0)
        self.assertIs(self.e.sens, Direction.OUVERTURE)
        self.assertAlmostEqual(self.e.position(1010.0), 25.0)
        self.assertAlmostEqual(self.e.position(1020.0), 50.0)
        self.assertEqual(self.e.position(1040.0), 100.0)

    def test_fermeture_utilise_le_temps_de_descente(self) -> None:
        self.e.definir_position(100)
        duree = self.e.demarrer(0, maintenant=0.0)
        self.assertAlmostEqual(duree, 20.0)
        self.assertIs(self.e.sens, Direction.FERMETURE)
        self.assertAlmostEqual(self.e.position(10.0), 50.0)

    def test_position_intermediaire_duree_partielle(self) -> None:
        # De 0 à 50 en montée : la moitié de 40 s.
        self.assertAlmostEqual(self.e.demarrer(50, 0.0), 20.0)
        # De 50 à 20 en descente : 30 % de 20 s.
        self.e.definir_position(50)
        self.assertAlmostEqual(self.e.demarrer(20, 0.0), 6.0)

    def test_pas_de_depassement_de_la_cible(self) -> None:
        self.e.demarrer(40, 0.0)
        self.assertEqual(self.e.position(10_000.0), 40.0)

    def test_arrivee(self) -> None:
        self.e.demarrer(100, 0.0)
        self.assertFalse(self.e.est_arrive(39.0))
        self.assertTrue(self.e.est_arrive(40.0))
        # Un minuteur peut partir quelques millisecondes trop tôt.
        self.assertTrue(self.e.est_arrive(39.97))
        self.assertAlmostEqual(self.e.duree_restante(30.0), 10.0)

    def test_terminer_fige_la_cible(self) -> None:
        self.e.demarrer(70, 0.0)
        self.assertEqual(self.e.terminer(), 70.0)
        self.assertFalse(self.e.en_mouvement)
        self.assertEqual(self.e.position(999.0), 70.0)

    def test_arret_au_milieu_du_trajet(self) -> None:
        self.e.demarrer(100, 0.0)
        position = self.e.arreter(20.0)
        self.assertAlmostEqual(position, 50.0)
        self.assertFalse(self.e.en_mouvement)
        # Le volet reste à 50 : le temps qui passe ne le fait plus bouger.
        self.assertAlmostEqual(self.e.position(500.0), 50.0)

    def test_nouvelle_cible_en_cours_de_route_meme_sens(self) -> None:
        self.e.demarrer(100, 0.0)  # monte
        # À t=20 s, le volet est à 50. Nouvelle cible : 80 → 30 % de 40 s = 12 s.
        duree = self.e.demarrer(80, 20.0)
        self.assertAlmostEqual(duree, 12.0)
        self.assertIs(self.e.sens, Direction.OUVERTURE)
        self.assertAlmostEqual(self.e.position(26.0), 65.0)

    def test_demi_tour_en_cours_de_route(self) -> None:
        self.e.demarrer(100, 0.0)  # monte
        # À t=20 s, le volet est à 50 ; on demande 25 : descente de 25 % de 20 s = 5 s.
        duree = self.e.demarrer(25, 20.0)
        self.assertAlmostEqual(duree, 5.0)
        self.assertIs(self.e.sens, Direction.FERMETURE)
        self.assertAlmostEqual(self.e.position(22.5), 37.5)

    def test_cible_deja_atteinte(self) -> None:
        self.e.definir_position(30)
        self.assertEqual(self.e.demarrer(30, 0.0), 0.0)
        self.assertFalse(self.e.en_mouvement)

    def test_position_arrondie(self) -> None:
        self.e.demarrer(100, 0.0)
        self.assertEqual(self.e.position_arrondie(0.0), 0)
        self.assertEqual(self.e.position_arrondie(10.0), 25)
        self.assertEqual(self.e.position_arrondie(39.7), 99)
        self.assertEqual(self.e.position_arrondie(39.9), 100)

    def test_positions_bornees(self) -> None:
        self.e.definir_position(150)
        self.assertEqual(self.e.position(0.0), 100.0)
        self.e.definir_position(-5)
        self.assertEqual(self.e.position(0.0), 0.0)
        self.e.demarrer(250, 0.0)
        self.assertEqual(self.e.cible, 100.0)

    def test_temps_invalides(self) -> None:
        with self.assertRaises(ValueError):
            TravelEstimator(0, 10)
        with self.assertRaises(ValueError):
            TravelEstimator(10, -1)
        with self.assertRaises(ValueError):
            self.e.definir_temps(0, 5)

    def test_changement_de_temps_sans_effet_sur_le_trajet_en_cours(self) -> None:
        self.e.demarrer(100, 0.0)  # 40 s prévues
        self.e.definir_temps(80, 80)
        self.assertAlmostEqual(self.e.position(20.0), 50.0)
        # Il s'applique au déplacement suivant.
        self.e.terminer()
        self.assertAlmostEqual(self.e.demarrer(0, 100.0), 80.0)


if __name__ == "__main__":
    unittest.main()
