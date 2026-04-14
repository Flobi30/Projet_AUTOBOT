#!/usr/bin/env python3
"""
Test minimal AUTOBOT V2 - Vérification pre-flight
Exécute avant de lancer le paper trading.
"""

import os
import sys

def check_environment():
    """Vérifie les variables d'environnement"""
    print("🔍 Vérification environnement...")
    
    key = os.getenv('KRAKEN_API_KEY')
    secret = os.getenv('KRAKEN_API_SECRET')
    
    if not key or not secret:
        print("⚠️  Clés API Kraken non définies")
        print("   Le bot démarrera en mode simulation")
        print("   Pour le trading réel, définissez:")
        print("   export KRAKEN_API_KEY='votre_key'")
        print("   export KRAKEN_API_SECRET='votre_secret'")
        return False
    else:
        print(f"✅ Clés API configurées (KEY: {key[:8]}...)")
        return True

def check_dependencies():
    """Vérifie les dépendances Python"""
    print("\n🔍 Vérification dépendances...")
    
    deps = [
        ('krakenex', 'API Kraken'),
        ('websocket', 'WebSocket client'),
        ('orjson', 'JSON parsing rapide (optionnel)'),
        ('fastapi', 'Dashboard API (optionnel)'),
        ('uvicorn', 'Serveur HTTP (optionnel)'),
    ]
    
    all_ok = True
    for module, desc in deps:
        try:
            __import__(module)
            print(f"✅ {desc} ({module})")
        except ImportError:
            print(f"❌ {desc} ({module}) - MANQUANT")
            all_ok = False
    
    return all_ok

def check_imports():
    """Vérifie que les modules AUTOBOT importent correctement"""
    print("\n🔍 Vérification imports AUTOBOT...")
    
    try:
        sys.path.insert(0, 'src')
        from autobot.v2.orchestrator import Orchestrator, InstanceConfig
        print("✅ Orchestrator")
        
        from autobot.v2.instance import TradingInstance
        print("✅ TradingInstance")
        
        from autobot.v2.order_executor import OrderExecutor
        print("✅ OrderExecutor")
        
        from autobot.v2.signal_handler import SignalHandler
        print("✅ SignalHandler")
        
        from autobot.v2.strategies import GridStrategy
        print("✅ GridStrategy")
        
        return True
    except Exception as e:
        print(f"❌ Erreur import: {e}")
        return False

def check_instance_creation():
    """Test création instance minimale"""
    print("\n🔍 Test création instance...")
    
    try:
        sys.path.insert(0, 'src')
        from autobot.v2.orchestrator import Orchestrator, InstanceConfig
        
        orch = Orchestrator()
        config = InstanceConfig(
            name="Test",
            symbol="XXBTZEUR",
            initial_capital=500.0,
            strategy="grid",
            leverage=1,
            grid_config={'range_percent': 7.0, 'num_levels': 5}
        )
        
        instance = orch.create_instance(config)
        if instance:
            print(f"✅ Instance créée: {instance.id}")
            print(f"✅ Capital disponible: {instance.get_available_capital():.2f}€")
            return True
        else:
            print("❌ Échec création instance")
            return False
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*60)
    print("🧪 TEST PRE-FLIGHT AUTOBOT V2")
    print("="*60)
    
    results = []
    
    results.append(("Environnement", check_environment()))
    results.append(("Dépendances", check_dependencies()))
    results.append(("Imports", check_imports()))
    results.append(("Création instance", check_instance_creation()))
    
    print("\n" + "="*60)
    print("📊 RÉSULTATS")
    print("="*60)
    
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_pass = all(r[1] for r in results)
    
    if all_pass:
        print("\n🎉 Tous les tests passent! Prêt pour paper trading.")
        print("\nProchaine étape:")
        print("  export KRAKEN_API_KEY='votre_key_paper'")
        print("  export KRAKEN_API_SECRET='votre_secret_paper'")
        print("  python3 -m autobot.v2.main")
        return 0
    else:
        print("\n⚠️  Certains tests ont échoué. Corrigez avant de continuer.")
        print("\nInstallation dépendances:")
        print("  pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())
