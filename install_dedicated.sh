#!/bin/bash
#
#

set -e
BOLD="\e[1m"
RESET="\e[0m"
GREEN="\e[32m"
RED="\e[31m"
BLUE="\e[34m"

echo -e "${BOLD}${GREEN}=== Installation d'AUTOBOT pour serveur dédié ===${RESET}"

if [[ $(id -u) -ne 0 ]]; then
    echo -e "${RED}Ce script doit être exécuté en tant que root${RESET}"
    exit 1
fi

echo -e "${BLUE}Installation des dépendances système...${RESET}"
apt-get update
apt-get install -y python3 python3-pip python3-venv git nginx supervisor lsb-release curl

echo -e "${BLUE}Création de l'utilisateur autobot...${RESET}"
id -u autobot &>/dev/null || useradd -m -s /bin/bash autobot

echo -e "${BLUE}Clonage du dépôt AUTOBOT...${RESET}"
if [ ! -d "/home/autobot/Projet_AUTOBOT" ]; then
    su - autobot -c "git clone https://github.com/Flobi30/Projet_AUTOBOT.git /home/autobot/Projet_AUTOBOT"
else
    su - autobot -c "cd /home/autobot/Projet_AUTOBOT && git pull"
fi

echo -e "${BLUE}Configuration de l'environnement Python...${RESET}"
su - autobot -c "cd /home/autobot/Projet_AUTOBOT && python3 -m venv venv"
su - autobot -c "cd /home/autobot/Projet_AUTOBOT && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

echo -e "${BLUE}Configuration de Nginx pour l'accès distant...${RESET}"
cat > /etc/nginx/sites-available/autobot << 'EOF'
server {
    listen 80;
    server_name _;  # Remplacer par votre nom de domaine si disponible

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

ln -sf /etc/nginx/sites-available/autobot /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

echo -e "${BLUE}Configuration de Supervisor...${RESET}"
mkdir -p /var/log/autobot
chown -R autobot:autobot /var/log/autobot

cat > /etc/supervisor/conf.d/autobot.conf << 'EOF'
[program:autobot]
command=/home/autobot/Projet_AUTOBOT/venv/bin/python -m src.autobot.main
directory=/home/autobot/Projet_AUTOBOT
user=autobot
autostart=true
autorestart=true
startretries=10
stdout_logfile=/var/log/autobot/autobot.log
stderr_logfile=/var/log/autobot/autobot_error.log
environment=PATH="/home/autobot/Projet_AUTOBOT/venv/bin:%(ENV_PATH)s"
EOF

systemctl enable supervisor
systemctl restart supervisor

echo -e "${BLUE}Configuration du démarrage automatique...${RESET}"
cat > /etc/systemd/system/autobot.service << 'EOF'
[Unit]
Description=AUTOBOT Service
After=network.target

[Service]
Type=forking
User=root
ExecStart=/usr/bin/supervisord
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable autobot.service

IP_ADDRESS=$(hostname -I | awk '{print $1}')
echo -e "${GREEN}${BOLD}Installation terminée!${RESET}"
echo -e "AUTOBOT est accessible à l'adresse: ${BOLD}http://$IP_ADDRESS${RESET}"
echo -e "Configurez les clés API en vous connectant à cette adresse."
