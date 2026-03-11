#!/bin/bash
# Script de test API Kraken - DRY-RUN uniquement

echo "🚀 Tests API Kraken - AUTOBOT V2"
echo "================================"
echo "🔒 Mode DRY-RUN: Aucun ordre réel ne sera placé"
echo ""

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
    echo "  export KRAKEN_API_SECRET='votre_secret'"
    echo "  ./test-kraken.sh --api-key 'votre_clé'"
    echo ""
    echo "⚠️  Note: Pour la sécurité, le secret n'est jamais accepté en argument."
    exit 1
fi

# Lance les tests
cd "$(dirname "$0")/../.."
python3 src/autobot/v2/tests/test_kraken_api.py "$@"
