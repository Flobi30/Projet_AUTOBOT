#!/bin/bash
# Script d'arrêt AUTOBOT V2

echo "🛑 Arrêt AUTOBOT V2..."

# Arrête les processus Python (le bot)
pkill -f "python.*autobot/v2/main.py" 2>/dev/null && echo "  ✅ Bot arrêté"

# Arrête les processus Node.js (le dashboard)
pkill -f "npm run dev" 2>/dev/null && echo "  ✅ Dashboard arrêté"

# Force kill si nécessaire
sleep 1
pkill -9 -f "python.*autobot/v2/main.py" 2>/dev/null
pkill -9 -f "npm run dev" 2>/dev/null

echo ""
echo "✅ Tous les services sont arrêtés"
