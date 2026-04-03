#!/bin/bash
# diagnose-autobot.sh — Diagnostic complet AutoBot V2
# Copier sur le serveur et exécuter : ./diagnose-autobot.sh

set -e

echo "🔍 DIAGNOSTIC AUTOBOT V2"
echo "========================"
echo ""

# 1. Vérifier si le conteneur tourne
echo "1. Status du conteneur Docker..."
if docker ps | grep -q autobot; then
    echo "   ✅ Conteneur actif"
    docker stats --no-stream autobot-v2 2>/dev/null || echo "   ⚠️  Stats indisponibles"
else
    echo "   ❌ Conteneur arrêté !"
    echo "   Dernier logs :"
    docker logs --tail 20 autobot-v2 2>/dev/null || echo "   Pas de logs disponibles"
fi
echo ""

# 2. Vérifier les logs en temps réel (10 dernières lignes)
echo "2. Dernières lignes de logs..."
docker logs --tail 50 autobot-v2 2>&1 | tail -50 || echo "   ❌ Pas de logs"
echo ""

# 3. Vérifier l'espace disque
echo "3. Espace disque..."
df -h / | tail -1
echo ""

# 4. Vérifier la mémoire
echo "4. Mémoire..."
free -h
echo ""

# 5. Vérifier le CPU
echo "5. Charge CPU..."
uptime
echo ""

# 6. Vérifier la connexion Kraken
echo "6. Test connexion réseau..."
ping -c 3 api.kraken.com > /dev/null 2>&1 && echo "   ✅ Kraken accessible" || echo "   ❌ Kraken inaccessible"
echo ""

# 7. Vérifier les fichiers de données
echo "7. Fichiers de données..."
if [ -d /opt/autobot/data ]; then
    echo "   ✅ Répertoire data existe"
    ls -lh /opt/autobot/data/
else
    echo "   ❌ Répertoire data manquant !"
fi
echo ""

# 8. Vérifier la configuration
echo "8. Configuration .env..."
if [ -f /opt/autobot/.env ]; then
    echo "   ✅ Fichier .env présent"
    echo "   Clés configurées :"
    grep -E "^(KRAKEN|DASHBOARD|ENV)" /opt/autobot/.env | sed 's/=.*$/=***/' || echo "   Aucune clé trouvée"
else
    echo "   ❌ Fichier .env manquant !"
fi
echo ""

# 9. Test endpoint health
echo "9. Test health endpoint..."
curl -s http://localhost:8080/health 2>/dev/null | head -20 || echo "   ❌ Health check failed"
echo ""

# 10. Résumé
echo "========================"
echo "📊 RÉSUMÉ"
echo "========================"
echo "Pour voir les logs en temps réel :"
echo "  docker logs -f autobot-v2"
echo ""
echo "Pour redémarrer :"
echo "  cd /opt/autobot && docker-compose restart"
echo ""
echo "Pour arrêter :"
echo "  cd /opt/autobot && docker-compose down"
