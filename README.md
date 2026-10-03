# Custom Cover Position (`timed_cover`)

Intégration Home Assistant qui **estime l'état et la position d'un ouvrant** (volet, store, porte…)
à partir de son temps d'ouverture et de son temps de fermeture complets, pour les ouvrants qui ne
renvoient pas leur position (par exemple les volets Somfy RTS pilotés par Overkiz).

Le nouvel ouvrant **se range sous l'appareil existant** : un seul appareil par ouvrant, pas de doublon.
Il peut aussi **reprendre le nom et l'identifiant de l'ouvrant d'origine** : les scripts et
automatisations existants l'utilisent alors sans modification.

> **État : version 0.3.0, en développement.** Testée dans une instance Home Assistant 2026.9.4 de test avec
> de faux ouvrants ; pas encore utilisée en production.

## Ce que l'on obtient

| | |
| --- | --- |
| État | Ouvert, fermé, ouverture en cours, fermeture en cours, indisponible. |
| Position | Pourcentage estimé de 0 (fermé) à 100 (ouvert). |
| Disponibilité | L'ouvrant est indisponible quand l'ouvrant d'origine l'est (l'état « inconnu » reste disponible : les volets RTS n'ont pas de retour d'état). |
| Attributs | `travel_time_up`, `travel_time_down` (secondes), `source_entity`, `target_position` pendant un déplacement. |
| Service | `timed_cover.set_known_position` : recale la position estimée sans faire bouger l'ouvrant. |

## Installation (manuelle)

1. Copier le dossier `custom_components/timed_cover` dans le dossier `custom_components` de Home Assistant.
2. Redémarrer Home Assistant.
3. Créer un ouvrant : **Paramètres → Appareils et services**, carte **Custom Cover Position**,
   bouton **Ajouter un ouvrant** (la première fois : **Ajouter une intégration**, puis chercher « Custom Cover Position »).

## Réglages

Les réglages sont affichés et expliqués dans l'interface (français et anglais). Ils se modifient avec la
roue dentée de l'ouvrant ; la position actuelle est conservée.

| Réglage | Rôle |
| --- | --- |
| Ouvrant réel à enrober | L'ouvrant qui reçoit les ordres (par exemple `cover.volet_salon_1_overkiz`). |
| Nom de l'ouvrant | Nom affiché ; l'identifiant en est déduit (`Volet Salon 1` donne `cover.volet_salon_1`). |
| Temps d'ouverture / de fermeture | Durée en secondes d'un trajet complet. |
| Envoyer « stop » aux extrémités | Envoie un ordre d'arrêt même après une ouverture ou une fermeture complète. Laisser désactivé sauf besoin. |
| Classe d'appareil | Les types de Home Assistant : volet, store, store vénitien, auvent, rideau, porte, portail, garage, clapet, fenêtre. |
| Désactiver les autres entités de l'appareil d'origine | Désactivé par défaut. Désactive tout sauf l'ouvrant d'origine (par exemple les boutons « My Position » d'Overkiz, qui commandent le volet sans passer par l'ouvrant et lui font perdre sa position estimée). Attention : les capteurs de l'appareil sont désactivés aussi. Tout est réactivé si l'option est décochée ou l'ouvrant supprimé. |
| Positions prédéfinies | Une liste (nom, pourcentage, icône facultative ; 8 au plus). Chaque ligne crée un bouton rangé sous l'appareil d'origine, nommé « <ouvrant> <position> », qui amène l'ouvrant à cette position. Les positions deviennent aussi les favoris de la fenêtre de l'ouvrant : « 0, vos positions, 100 » (sans position, les favoris par défaut restent ; une modification faite à la main dans la fenêtre est respectée jusqu'au prochain changement de la liste). |
| Masquer l'ouvrant d'origine | L'original disparaît des écrans automatiques (il reste dans les listes de choix des scripts) ; il réapparaît si l'ouvrant est supprimé. |
| Reprendre le nom et l'identifiant de l'ouvrant d'origine | Activé par défaut. Seulement à la création, et seulement si le nom saisi donne l'identifiant de l'original : l'original est renommé avec le suffixe choisi (`cover.volet_cuisine_origine`), le nouvel ouvrant prend `cover.volet_cuisine`. À la suppression, tout est remis. Désactivé : le nouvel ouvrant reçoit un autre identifiant (`cover.volet_cuisine_2`). |
| Suffixe de l'ouvrant d'origine | Ajouté au nom et à l'identifiant de l'original quand il est renommé (« origine » en français, « source » sinon). |

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
