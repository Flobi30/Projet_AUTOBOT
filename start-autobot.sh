#!/bin/bash
# Script de démarrage complet AUTOBOT V2 + Dashboard

echo "🚀 Démarrage AUTOBOT V2 avec Dashboard"
echo "======================================="
echo ""

# Vérifie si on est dans le bon répertoire
if [ ! -f "src/autobot/v2/main_async.py" ]; then
    echo "❌ Erreur: Vous devez être à la racine du projet"
    exit 1
fi

# Vérifie les dépendances Python
echo "📦 Vérification dépendances Python..."
pip install -q -r src/autobot/v2/api/requirements.txt 2>/dev/null || true

# Vérifie les dépendances Node.js pour le dashboard
if [ -d "dashboard" ]; then
    echo "📦 Vérification dépendances Dashboard..."
    cd dashboard
    npm install --silent 2>/dev/null || true
    cd ..
fi

echo ""
echo "🔧 Configuration:"
echo "  - Bot API: http://localhost:8080"
echo "  - Dashboard: http://localhost:5173 (développement)"
echo ""

# Lance le bot Python ASYNC officiel en arrière-plan
echo "🤖 Démarrage du bot..."
python3 src/autobot/v2/main_async.py &
BOT_PID=$!

# Attend que l'API soit prête
echo "⏳ Attente du démarrage de l'API..."
sleep 3

# Vérifie si l'API répond
if curl -s http://localhost:8080/api/status > /dev/null 2>&1; then
    echo "✅ API Bot démarrée"
else
    echo "⚠️  API non accessible (le bot continue de démarrer)"
fi

# Lance le dashboard React en arrière-plan (si installé)
if [ -d "dashboard" ]; then
    echo "🌐 Démarrage Dashboard React..."
    cd dashboard
    npm run dev &
    DASHBOARD_PID=$!
    cd ..
    
    echo ""
    echo "======================================="
    echo "✅ Tous les services sont démarrés!"
    echo "======================================="
    echo ""
    echo "📊 Dashboard: http://localhost:5173"
    echo "📈 API Bot:   http://localhost:8080/api/status"
    echo "📝 Logs:      tail -f autobot_async.log"
    echo ""
    echo "🛑 Pour arrêter: Ctrl+C ou ./stop-autobot.sh"
    echo ""
    
    # Attend que l'utilisateur arrête
    wait $BOT_PID $DASHBOARD_PID
else
    echo ""
    echo "======================================="
    echo "✅ Bot démarré (sans dashboard)"
    echo "======================================="
    echo ""
    echo "📈 API: http://localhost:8080/api/status"
    echo ""
    
    wait $BOT_PID
fi
