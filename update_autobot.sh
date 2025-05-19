#!/bin/bash
#
#

set -e
BOLD="\e[1m"
RESET="\e[0m"
GREEN="\e[32m"
RED="\e[31m"
BLUE="\e[34m"

echo -e "${BOLD}${GREEN}=== Mise à jour d'AUTOBOT ===${RESET}"

echo -e "${BLUE}Arrêt temporaire du service...${RESET}"
supervisorctl stop autobot

echo -e "${BLUE}Mise à jour du code source...${RESET}"
su - autobot -c "cd /home/autobot/Projet_AUTOBOT && git pull"

echo -e "${BLUE}Mise à jour des dépendances...${RESET}"
su - autobot -c "cd /home/autobot/Projet_AUTOBOT && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

echo -e "${BLUE}Redémarrage du service...${RESET}"
supervisorctl start autobot

echo -e "${GREEN}${BOLD}Mise à jour terminée!${RESET}"
