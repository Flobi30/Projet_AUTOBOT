#!/bin/bash
# start-paper.sh — Lancer AutoBot V2 en mode Paper Trading

set -e

echo "🚀 AutoBot V2 — Paper Trading Mode"
echo "==================================="
echo ""

# Vérifier .env
if [ ! -f .env ]; then
    echo "❌ Fichier .env manquant !"
    echo "Copiez .env.example vers .env et configurez vos clés API."
    exit 1
fi

# Vérifier que c'est bien du sandbox
if grep -q "PAPER_TRADING=false" .env; then
    echo "⚠️  ATTENTION: PAPER_TRADING=false détecté !"
    read -p "Voulez-vous vraiment lancer en mode LIVE ? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Annulé. Modifiez .env pour PAPER_TRADING=true"
        exit 1
    fi
fi

# Créer répertoires
mkdir -p data logs

# Validation pré-lancement (helper opérateur)
if [ -f tools/paper_ops.py ]; then
    echo "🧪 Validation pre-launch (.env)..."
    python tools/paper_ops.py validate --env-file .env || {
        echo "❌ Validation paper échouée. Corrigez .env puis relancez."
        exit 1
    }
fi

# Lancer
echo "📦 Démarrage des conteneurs..."
docker-compose up --build -d

echo ""
echo "✅ AutoBot démarré !"
echo ""
echo "📊 Dashboard: http://localhost:8080"
echo "📜 Logs: docker-compose logs -f"
echo "🛑 Arrêter: docker-compose down"
echo ""
echo "Mode: 📝 PAPER TRADING (pas d'argent réel)"
