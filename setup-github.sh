#!/usr/bin/env bash
# Creates the GitHub repository and pushes this project to it.
#
# Needs the GitHub CLI: https://cli.github.com/  (brew install gh / apt install gh)
# Run `gh auth login` once first.
set -euo pipefail

OWNER="${OWNER:-Manzo76}"
REPO_NAME="${1:-ha-motorcycle-racing-2}"
VISIBILITY="${2:-public}"

git init -b main
git add .
git commit -m "Motorcycle Racing integration for Home Assistant"

gh repo create "$OWNER/$REPO_NAME" --"$VISIBILITY" --source=. --remote=origin --push

# HACS shows the description and topics, so set them while we are here.
gh repo edit --description "Motorcycle racing integration for Home Assistant: MotoGP, WorldSBK and more, with a custom dashboard card"
gh repo edit --add-topic home-assistant --add-topic hacs --add-topic motogp \
             --add-topic worldsbk --add-topic custom-component --add-topic motorcycle-racing

gh release create v0.1.0 --title "v0.1.0" --notes "First release."

echo
echo "Done. In Home Assistant: HACS -> Custom repositories -> add"
gh repo view --json url -q .url
