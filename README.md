# Volets à temps de trajet (`timed_cover`)

Intégration Home Assistant qui **estime la position d'un volet roulant** à partir de son temps de montée
et de son temps de descente, pour les volets qui ne renvoient pas leur position (par exemple les volets
Somfy RTS pilotés par Overkiz).

Le nouveau volet **se range sous l'appareil existant** du volet : un seul appareil par volet, pas de
doublon, et l'entité d'origine peut être masquée pour ne pas être utilisée par erreur.

> **État : version 0.1.0, en développement.** Testée dans une instance Home Assistant 2026.9.4 de test avec
> de faux volets ; pas encore utilisée en production.

## Ce que l'on obtient

| | |
| --- | --- |
| État | Ouvert, fermé, ouverture en cours, fermeture en cours, indisponible. |
| Position | Pourcentage estimé de 0 (fermé) à 100 (ouvert). |
| Disponibilité | Le volet est indisponible quand le volet d'origine l'est (l'état « inconnu » reste disponible : les volets RTS n'ont pas de retour d'état). |
| Attributs | `travel_time_up`, `travel_time_down` (secondes), `source_entity`, `target_position` pendant un déplacement. |
| Service | `timed_cover.set_known_position` : recale la position estimée sans faire bouger le volet. |

## Installation (manuelle)

1. Copier le dossier `custom_components/timed_cover` dans le dossier `custom_components` de Home Assistant.
2. Redémarrer Home Assistant.
3. Créer un volet : **Paramètres → Appareils et services**, onglet **Entrées**, **Créer une entrée**,
   puis **Volets à temps de trajet**. (Chemin à confirmer dans l'interface.)

## Réglages

Les réglages sont affichés et expliqués dans l'interface, en français. Ils se modifient avec le bouton
**Configurer** de l'entrée ; la position actuelle du volet est conservée.

| Réglage | Rôle |
| --- | --- |
| Volet réel à enrober | Le volet qui reçoit les ordres (par exemple `cover.volet_salon_1_overkiz`). |
| Nom du volet | Nom affiché ; l'identifiant en est déduit (`Volet Salon 1` donne `cover.volet_salon_1`). |
| Temps de montée / de descente | Durée en secondes d'un trajet complet. |
| Envoyer « stop » aux extrémités | Envoie un ordre d'arrêt même après une ouverture ou une fermeture complète. Laisser désactivé sauf besoin. |
| Type de volet | Volet roulant, store, store banne, rideau, voilage ou fenêtre. |
| Masquer le volet d'origine | Le volet d'origine n'apparaît plus dans l'interface ; il est ré-affiché si le volet à temps de trajet est supprimé. |

## Comment ça marche

- **Ouvrir / Fermer** : l'ordre est envoyé au volet réel, et la position est estimée à 100 ou 0 à la fin
  du temps de trajet. L'ordre est toujours envoyé, même si la position estimée est déjà à l'extrémité,
  ce qui permet de recaler un volet qui a dérivé.
- **Aller à une position** : un ordre d'ouverture ou de fermeture est envoyé, puis un ordre d'arrêt à
  l'instant calculé. Si le volet va déjà dans le bon sens, seule l'heure d'arrêt change.
- **Plusieurs volets à la fois** (script de groupe) : chaque volet est indépendant et ses ordres sont
  exécutés l'un après l'autre grâce à un verrou propre au volet.
- **Redémarrage de Home Assistant** : la dernière position est restaurée.

La position est une **estimation** : elle peut dériver avec le temps (commande faite à la télécommande,
par exemple). Un ordre Ouvrir ou Fermer complet, ou le service `set_known_position`, la recale.

## Développement

```
python3 -m unittest discover -s tests -v          # tests de l'estimateur (sans Home Assistant)
./tools/deployer-sandbox.sh --redemarrer          # copie dans la VM de test et redémarre
python3 tools/essai_sandbox.py                    # scénarios complets sur la VM de test
```

Les scénarios utilisent l'intégration `demo` de Home Assistant comme faux volets. Les outils supposent la
VM de test décrite dans le projet de contexte (`projet-ha-sandbox`) et un jeton dans `~/.ha-sandbox-token`.

## Licence

MIT. Le principe (position proportionnelle au temps écoulé) est celui de la famille d'intégrations
`cover_time_based` ; le code est ré-écrit.
