#!/bin/bash
# Déploie l'intégration dans la VM ha-sandbox (partage Samba monté sur /Volumes/config)
# et, avec l'option --redemarrer, redémarre Home Assistant par son API.
#
# Prérequis : le partage « config » de la sandbox est monté (Finder, ⌘K, smb://10.10.30.30)
# et le jeton de l'API est dans ~/.ha-sandbox-token (il n'est jamais affiché).
set -euo pipefail

DEST="/Volumes/config/custom_components/timed_cover/"
SRC="$(cd "$(dirname "$0")/.." && pwd)/custom_components/timed_cover/"
URL="http://10.10.30.30"

[ -d /Volumes/config ] || { echo "Le partage /Volumes/config n'est pas monté." >&2; exit 1; }
mkdir -p "$DEST"
# --inplace : écrit sous le nom final (les noms temporaires en « .xxx » sont refusés par Samba).
rsync -rt --inplace --delete --exclude='__pycache__' --exclude='.DS_Store' "$SRC" "$DEST"
echo "Intégration copiée dans la sandbox."

if [ "${1:-}" = "--redemarrer" ]; then
  curl -s -m 20 -o /dev/null -X POST -H "Authorization: Bearer $(cat ~/.ha-sandbox-token)" \
       -H "Content-Type: application/json" -d '{}' "$URL/api/services/homeassistant/restart" || true
  echo "Redémarrage demandé, attente du retour de l'API..."
  sleep 15
  for _ in $(seq 1 40); do
    code=$(curl -s -m 5 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $(cat ~/.ha-sandbox-token)" "$URL/api/" || true)
    [ "$code" = "200" ] && { echo "Home Assistant est de nouveau disponible."; exit 0; }
    sleep 5
  done
  echo "Home Assistant ne répond pas après le redémarrage." >&2
  exit 1
fi
