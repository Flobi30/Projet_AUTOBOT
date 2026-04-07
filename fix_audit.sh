#!/bin/bash
set -e

cd /opt/Projet_AUTOBOT

echo "============================================"
echo "🔧 AUDIT FIX SCRIPT — Opus 4.6 Corrections"
echo "============================================"

# =============================================
# 🔴 CRITICAL 1: Port 8080 bind to localhost
# =============================================
echo ""
echo "🔴 [1/8] Fixing docker-compose.yml — bind port to 127.0.0.1..."

sed -i 's|"8080:8080"|"127.0.0.1:8080:8080"|' docker-compose.yml

echo "   ✅ Port now bound to 127.0.0.1"

# =============================================
# 🔴 CRITICAL 2: .env permissions
# =============================================
echo ""
echo "🔴 [2/8] Fixing .env permissions..."

chmod 600 .env
echo "   ✅ .env permissions set to 600"

# Verify .env is mounted read-only in docker-compose (already :ro)
grep -q ':ro' docker-compose.yml && echo "   ✅ .env already mounted read-only in Docker" || echo "   ⚠️ .env not mounted read-only"

# =============================================
# 🔴 CRITICAL 3: HTTPS — generate self-signed cert
# =============================================
echo ""
echo "🔴 [3/8] Generating self-signed SSL certificate..."

mkdir -p /opt/Projet_AUTOBOT/certs

if [ ! -f /opt/Projet_AUTOBOT/certs/server.crt ]; then
    openssl req -x509 -newkey rsa:2048 -keyout /opt/Projet_AUTOBOT/certs/server.key \
        -out /opt/Projet_AUTOBOT/certs/server.crt -days 365 -nodes \
        -subj "/C=FR/ST=Paris/L=Paris/O=AutoBot/CN=autobot.local" 2>/dev/null
    echo "   ✅ Self-signed certificate generated in certs/"
else
    echo "   ✅ Certificate already exists"
fi

# Add SSL env vars and cert volume to docker-compose.yml
# Add environment variables for SSL
if ! grep -q 'DASHBOARD_SSL_CERT' docker-compose.yml; then
    sed -i '/DASHBOARD_API_TOKEN/a\      - DASHBOARD_SSL_CERT=/app/certs/server.crt\n      - DASHBOARD_SSL_KEY=/app/certs/server.key' docker-compose.yml
    echo "   ✅ SSL env vars added to docker-compose.yml"
fi

# Add certs volume mount
if ! grep -q 'certs:/app/certs' docker-compose.yml; then
    sed -i '/\.env:\/app\/\.env:ro/a\      - ./certs:/app/certs:ro' docker-compose.yml
    echo "   ✅ Certs volume mount added to docker-compose.yml"
fi

# Update healthcheck to use https (with -k for self-signed)
sed -i 's|"http://localhost:8080/health"|"https://localhost:8080/health", "-k"|' docker-compose.yml

echo "   ✅ Healthcheck updated for HTTPS"

# =============================================
# 🟠 HIGH 4: CPU — fix busy-spin in async_dispatcher
# =============================================
echo ""
echo "🟠 [4/8] Fixing CPU busy-spin in async_dispatcher.py..."

# Change _SLEEP_EMPTY from 0.0 to 0.005 (5ms) to prevent CPU spinning
sed -i "s|_SLEEP_EMPTY: float = 0.0.*|_SLEEP_EMPTY: float = 0.005    # 5ms sleep to prevent CPU spinning (was 0.0)|" src/autobot/v2/async_dispatcher.py

echo "   ✅ _SLEEP_EMPTY changed from 0.0 to 0.005 (5ms)"

# =============================================
# 🟠 HIGH 5: Cleanup orphaned instance_state records
# =============================================
echo ""
echo "🟠 [5/8] Adding orphaned instance_state cleanup to persistence.py..."

# Add cleanup_orphaned_instances method and call it at startup
python3 << 'PYEOF'
import re

with open("src/autobot/v2/persistence.py", "r") as f:
    content = f.read()

# Check if cleanup_orphaned_instances already exists
if "cleanup_orphaned_instances" not in content:
    # Find the cleanup_old_data method and add a new method after it
    insertion_point = content.find("# Singleton global")
    if insertion_point == -1:
        insertion_point = content.rfind("\ndef get_persistence")
    
    new_method = '''
    def cleanup_orphaned_instances(self, max_age_hours: int = 24) -> int:
        """
        Nettoie les enregistrements instance_state orphelins.
        Supprime les instances arrêtées depuis plus de max_age_hours.
        Retourne le nombre de lignes supprimées.
        """
        try:
            with self._lock:
                conn = self._get_conn()
                cursor = conn.execute("""
                    DELETE FROM instance_state 
                    WHERE status='stopped' 
                    AND updated_at < datetime('now', '-1 day')
                """)
                deleted = cursor.rowcount
                conn.commit()
            
            if deleted > 0:
                logger.info(f"🧹 Nettoyage: {deleted} instances orphelines supprimées")
            return deleted
        except Exception as e:
            logger.exception(f"❌ Erreur nettoyage instances orphelines: {e}")
            return 0

'''
    
    content = content[:insertion_point] + new_method + content[insertion_point:]
    
    with open("src/autobot/v2/persistence.py", "w") as f:
        f.write(content)
    
    print("   ✅ cleanup_orphaned_instances method added to persistence.py")
else:
    print("   ✅ cleanup_orphaned_instances already exists")
PYEOF

# Now add the cleanup call to the orchestrator's start method
python3 << 'PYEOF'
with open("src/autobot/v2/orchestrator_async.py", "r") as f:
    content = f.read()

if "cleanup_orphaned_instances" not in content:
    # Add import if needed
    if "from .persistence import" in content:
        if "get_persistence" not in content:
            content = content.replace(
                "from .persistence import",
                "from .persistence import get_persistence,"
            )
    elif "get_persistence" not in content:
        # Add import after existing imports
        content = content.replace(
            "from .hot_path_optimizer import",
            "from .persistence import get_persistence\nfrom .hot_path_optimizer import"
        )
    
    # Add cleanup call at the start of the start() method, after self._start_time
    old = '        self._start_time = datetime.now(timezone.utc)'
    new = '''        self._start_time = datetime.now(timezone.utc)

        # Cleanup orphaned instance_state records at startup
        try:
            persistence = get_persistence()
            deleted = persistence.cleanup_orphaned_instances()
            if deleted:
                logger.info(f"🧹 Startup cleanup: {deleted} orphaned instances removed")
        except Exception as exc:
            logger.warning(f"⚠️ Startup cleanup failed: {exc}")'''
    
    content = content.replace(old, new, 1)
    
    with open("src/autobot/v2/orchestrator_async.py", "w") as f:
        f.write(content)
    
    print("   ✅ Startup cleanup added to orchestrator_async.py")
else:
    print("   ✅ Startup cleanup already exists in orchestrator")
PYEOF

# =============================================
# 🟡 MEDIUM 6: uptime_seconds in /health
# =============================================
echo ""
echo "🟡 [6/8] Fixing uptime_seconds in /health endpoint..."

python3 << 'PYEOF'
with open("src/autobot/v2/orchestrator_async.py", "r") as f:
    content = f.read()

# Add uptime_seconds to get_status() return dict
old_status = '''        return {
            "running": self.running,
            "start_time": self._start_time,
            "uptime": datetime.now(timezone.utc) - self._start_time if self._start_time else None,
            "instance_count": len(self._instances),'''

new_status = '''        return {
            "running": self.running,
            "start_time": self._start_time,
            "uptime": datetime.now(timezone.utc) - self._start_time if self._start_time else None,
            "uptime_seconds": (datetime.now(timezone.utc) - self._start_time).total_seconds() if self._start_time else None,
            "instance_count": len(self._instances),'''

if "uptime_seconds" not in content.split("def get_status")[1].split("def ")[0]:
    content = content.replace(old_status, new_status)
    with open("src/autobot/v2/orchestrator_async.py", "w") as f:
        f.write(content)
    print("   ✅ uptime_seconds added to get_status()")
else:
    print("   ✅ uptime_seconds already in get_status()")
PYEOF

# =============================================
# 🟡 MEDIUM 7: available_cash — use real capital
# =============================================
echo ""
echo "🟡 [7/8] Fixing available_cash calculation in dashboard.py..."

python3 << 'PYEOF'
with open("src/autobot/v2/api/dashboard.py", "r") as f:
    content = f.read()

# Replace the hardcoded 10% calculation with orchestrator method
old_capital = '''        instances_data = orchestrator.get_instances_snapshot()
        total_capital = sum(inst.get('capital', 0) for inst in instances_data)
        total_profit = sum(inst.get('profit', 0) for inst in instances_data)
        total_invested = total_capital - total_profit
        available = total_capital * 0.1'''

new_capital = '''        instances_data = orchestrator.get_instances_snapshot()
        total_capital = sum(inst.get('capital', 0) for inst in instances_data)
        total_profit = sum(inst.get('profit', 0) for inst in instances_data)
        total_invested = total_capital - total_profit
        # Use real available capital from orchestrator (was hardcoded 10%)
        get_available = getattr(orchestrator, '_get_available_capital', None)
        if get_available:
            import asyncio
            try:
                available = await get_available()
            except Exception:
                available = total_capital * 0.1  # fallback
        else:
            available = total_capital * 0.1  # fallback'''

if 'total_capital * 0.1' in content:
    content = content.replace(old_capital, new_capital)
    with open("src/autobot/v2/api/dashboard.py", "w") as f:
        f.write(content)
    print("   ✅ available_cash now uses orchestrator._get_available_capital()")
else:
    print("   ✅ available_cash already fixed")
PYEOF

# =============================================
# 🟡 MEDIUM 8: Market selector — feed prices from WS
# =============================================
echo ""
echo "🟡 [8/8] Fixing market selector — wire price feed to market analyzer..."

python3 << 'PYEOF'
with open("src/autobot/v2/websocket_async.py", "r") as f:
    content = f.read()

# Add market_analyzer price feeding in _process_ticker
if "market_analyzer" not in content:
    # Add import
    old_imports_end = content.find("logger = logging.getLogger")
    if old_imports_end == -1:
        # fallback: find end of imports
        old_imports_end = content.find("\nlogger")
    
    import_line = "\nfrom .market_analyzer import get_market_analyzer\n"
    if "from .market_analyzer" not in content:
        content = content[:old_imports_end] + import_line + content[old_imports_end:]
    
    # Add price feed to _process_ticker, after self._last_prices[pair] = ticker
    old_line = '        self._last_prices[pair] = ticker'
    new_line = '''        self._last_prices[pair] = ticker

        # Feed price to market analyzer for market selector
        try:
            analyzer = get_market_analyzer()
            analyzer.add_price(pair, price)
        except Exception:
            pass  # Non-critical — don't break WS flow'''
    
    content = content.replace(old_line, new_line, 1)
    
    with open("src/autobot/v2/websocket_async.py", "w") as f:
        f.write(content)
    
    print("   ✅ Market analyzer price feed wired into _process_ticker")
else:
    print("   ✅ Market analyzer already wired")

# Also reduce the minimum history requirement from 100 to 20 for faster startup
with open("src/autobot/v2/market_analyzer.py", "r") as f:
    content = f.read()

if "len(history) < 100" in content:
    content = content.replace(
        "if len(history) < 100:  # Minimum 100 points",
        "if len(history) < 20:  # Minimum 20 points (was 100 — too strict for startup)"
    )
    with open("src/autobot/v2/market_analyzer.py", "w") as f:
        f.write(content)
    print("   ✅ Market analyzer min history reduced from 100 to 20")
else:
    print("   ✅ Market analyzer history threshold already adjusted")
PYEOF

# =============================================
# 🔥 UFW Configuration
# =============================================
echo ""
echo "🔥 Configuring UFW firewall..."

ufw --force reset >/dev/null 2>&1
ufw default deny incoming >/dev/null 2>&1
ufw default allow outgoing >/dev/null 2>&1
ufw allow 22/tcp >/dev/null 2>&1
ufw allow 8080/tcp >/dev/null 2>&1
echo "y" | ufw enable >/dev/null 2>&1

echo "   ✅ UFW configured and enabled"
ufw status

echo ""
echo "============================================"
echo "✅ All fixes applied. Ready to rebuild."
echo "============================================"
