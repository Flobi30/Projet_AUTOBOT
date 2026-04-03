#!/bin/bash
# install-hetzner.sh — Installation complète AutoBot V2 sur Hetzner
# À copier sur le serveur et exécuter : ./install-hetzner.sh

set -e

echo "🚀 INSTALLATION AUTOBOT V2 SUR HETZNER"
echo "======================================="
echo ""

# 1. Mise à jour système
echo "1. Mise à jour système..."
apt update && apt upgrade -y
echo "   ✅ Système à jour"
echo ""

# 2. Installation Docker
echo "2. Installation Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "   ✅ Docker installé"
else
    echo "   ✅ Docker déjà présent"
fi
echo ""

# 3. Installation Docker Compose
echo "3. Installation Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    apt install -y docker-compose
    echo "   ✅ Docker Compose installé"
else
    echo "   ✅ Docker Compose déjà présent"
fi
echo ""

# 4. Création répertoire
echo "4. Création répertoire /opt/autobot..."
mkdir -p /opt/autobot
cd /opt/autobot

# 5. Clone du repo
echo "5. Clone du repository..."
if [ -d "/opt/autobot/.git" ]; then
    echo "   ✅ Repo déjà présent, mise à jour..."
    git pull origin master
else
    git clone https://github.com/Flobi30/Projet_AUTOBOT.git /opt/autobot
    echo "   ✅ Repo cloné"
fi
echo ""

# 6. Configuration
echo "6. Configuration..."
if [ ! -f "/opt/autobot/.env" ]; then
    cat > /opt/autobot/.env << 'EOF'
# === KRAKEN API (SANDBOX pour paper trading) ===
# Remplacez par vos clés : https://support.kraken.com/hc/en-us/articles/360000906026
KRAKEN_API_KEY=votre_cle_sandbox_ici
KRAKEN_API_SECRET=votre_secret_sandbox_ici

# === ENVIRONNEMENT ===
ENV=production
LOG_LEVEL=INFO

# === DASHBOARD ===
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8080
DASHBOARD_API_TOKEN=votre_token_securise_au_hasard_12345

# === TRADING CONFIG ===
INITIAL_CAPITAL=100
MAX_INSTANCES=50
PAPER_TRADING=true
EOF
    chmod 600 /opt/autobot/.env
    echo "   ✅ Fichier .env créé (À MODIFIER avec tes clés !)"
else
    echo "   ✅ Fichier .env déjà présent"
fi
echo ""

# 7. Création répertoires data/logs
echo "7. Création répertoires..."
mkdir -p /opt/autobot/data /opt/autobot/logs
chmod 755 /opt/autobot/data /opt/autobot/logs
echo "   ✅ Répertoires créés"
echo ""

# 8. Build et lancement
echo "8. Build et lancement..."
cd /opt/autobot
docker-compose build
docker-compose up -d
echo "   ✅ Conteneurs démarrés"
echo ""

# 9. Vérification
echo "9. Vérification..."
sleep 5
if docker ps | grep -q autobot; then
    echo "   ✅ AutoBot est en ligne !"
    echo ""
    echo "📊 Dashboard : http://$(curl -s ifconfig.me):8080"
    echo "📜 Logs : docker logs -f autobot-v2"
    echo ""
else
    echo "   ❌ Problème au démarrage"
    echo "   Logs d'erreur :"
    docker logs autobot-v2 2>&1 | tail -20
fi

echo ""
echo "========================"
echo "🎉 INSTALLATION TERMINÉE"
echo "========================"
echo ""
echo "Prochaines étapes :"
echo "1. Modifier /opt/autobot/.env avec tes vraies clés API Kraken"
echo "2. Redémarrer : docker-compose restart"
echo "3. Voir les logs : docker logs -f autobot-v2"
echo ""
echo "Commandes utiles :"
echo "  ./diagnose-autobot.sh  → Voir si tout va bien"
echo "  docker-compose logs -f → Voir les logs temps réel"
echo "  docker-compose restart → Redémarrer le bot"
