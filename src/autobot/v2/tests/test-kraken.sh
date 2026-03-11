#!/bin/bash
# Script de test API Kraken

echo "🚀 Tests API Kraken - AUTOBOT V2"
echo "================================"

# Vérifie si krakenex est installé
python3 -c "import krakenex" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 Installation de krakenex..."
    pip install krakenex
fi

# Vérifie les variables d'environnement
if [ -z "$KRAKEN_API_KEY" ] || [ -z "$KRAKEN_API_SECRET" ]; then
    echo ""
    echo "⚠️  Variables d'environnement manquantes!"
    echo ""
    echo "Définissez vos clés:"
    echo "  export KRAKEN_API_KEY='votre_clé'"
    echo "  export KRAKEN_API_SECRET='votre_secret'"
    echo ""
    echo "Ou utilisez:"
    echo "  ./test-kraken.sh --api-key XXX --api-secret YYY"
    exit 1
fi

# Lance les tests
cd "$(dirname "$0")/../.."
python3 src/autobot/v2/tests/test_kraken_api.py "$@"
