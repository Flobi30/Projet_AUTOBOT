#!/bin/bash


echo "🔒 Déploiement des améliorations de sécurité pour AUTOBOT..."

cd /home/autobot/Projet_AUTOBOT
git pull origin devin/1747921994-security-enhancements

sudo mkdir -p /var/log/autobot
sudo chown -R autobot:autobot /var/log/autobot

chmod +x deploy_security.sh

if ! grep -q "AUTOBOT_RATE_LIMIT" .env; then
    echo "Ajout des variables d'environnement de sécurité..."
    cat >> .env << EOF
AUTOBOT_RATE_LIMIT=5
AUTOBOT_RATE_LIMIT_WINDOW=60
AUTOBOT_BLOCK_DURATION=300
AUTOBOT_WAF_MAX_STRIKES=3
AUTOBOT_ATTACK_THRESHOLD=3
AUTOBOT_LOG_FILE=/var/log/autobot/security.log
AUTOBOT_BLOCK_IP=187.234.19.188
EOF
fi

sudo supervisorctl restart autobot

echo "✅ Déploiement terminé. Vérifiez les logs pour confirmer que tout fonctionne correctement."
echo "   tail -f /var/log/autobot/autobot.log"
echo "   tail -f /var/log/autobot/security.log"
