# Développement

Ce document s'adresse à celles et ceux qui veulent modifier l'intégration. Le [README](README.md) s'adresse aux utilisateurs.

## Outils

```
python3 -m unittest discover -s tests -v          # tests de l'estimateur (sans Home Assistant)
./tools/deployer-sandbox.sh --redemarrer          # copie dans la VM de test et redémarre
python3 tools/essai_sandbox.py                    # scénarios complets sur la VM de test
python3 tools/tableau_textes.py fichier.md        # tableau anglais/français des textes, pour relecture
```

Les scénarios utilisent l'intégration `demo` de Home Assistant comme fausses entités. Les outils supposent une instance Home Assistant de test et un jeton dans `~/.ha-sandbox-token`. Les textes affichés sont dans `custom_components/timed_cover/strings.json` (anglais, référence technique) et `translations/` (une langue par fichier) ; le français fait foi.

## Comment ça marche

- **Ouvrir / Fermer** : la commande est envoyée à l'entité source, et la position est estimée à 100 % ou 0 % à la fin du délai.
- **Aller à une position** : une commande d'ouverture ou de fermeture est envoyée, puis une commande d'arrêt à l'instant calculé. Si le volet va déjà dans le bon sens, seule l'heure d'arrêt change.
- **Plusieurs entités à la fois** (script de groupe) : chaque entité personnalisée est indépendante ; ses commandes passent l'une après l'autre grâce à un verrou qui lui est propre.
- **Redémarrage de Home Assistant** : la dernière position est restaurée.
- **Disponibilité** : l'entité personnalisée est indisponible quand l'entité source l'est ; l'état « inconnu » reste disponible.
- **Entité source** : retrouvée par son identifiant interne du registre (et non par son nom), ce qui lui permet d'être renommée sans que l'intégration la perde.

## Icône

L'icône est dans `custom_components/timed_cover/brand/` : `icon.png` (256 × 256) et `icon@2x.png` (512 × 512), fond transparent. Le dessin source, modifiable avec Inkscape, est `assets/icon-source.svg`. Home Assistant ne la prend en compte qu'après un redémarrage.
