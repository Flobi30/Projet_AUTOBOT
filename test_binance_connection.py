#!/usr/bin/env python3
"""
Script de test connexion Binance Testnet - AUTOBOT
Exécute ce script sur ta machine pour vérifier que tout marche.
"""

import os
import sys

def check_installation():
    """Vérifie que python-binance est installé"""
    try:
        from binance.client import Client
        print("✅ python-binance est installé")
        return True
    except ImportError:
        print("❌ python-binance n'est pas installé")
        print("\nInstalle-le avec:")
        print("  pip install python-binance")
        return False

def test_connection():
    """Test la connexion à Binance Testnet"""
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    
    # Récupère les clés depuis les variables d'environnement
    api_key = os.getenv('BINANCE_TESTNET_API_KEY')
    api_secret = os.getenv('BINANCE_TESTNET_API_SECRET')
    
    if not api_key or not api_secret:
        print("\n❌ Clés API manquantes!")
        print("\nDéfinis les variables d'environnement:")
        print("  export BINANCE_TESTNET_API_KEY='ta_cle'")
        print("  export BINANCE_TESTNET_API_SECRET='ton_secret'")
        return False
    
    print(f"\n🔑 Clé API trouvée: {api_key[:10]}...")
    
    try:
        # Crée le client
        print("\n🔄 Connexion à Binance Testnet...")
        client = Client(api_key=api_key, api_secret=api_secret, testnet=True)
        
        # Test 1: Ping
        client.ping()
        print("✅ Ping serveur: OK")
        
        # Test 2: Récupère le temps serveur
        server_time = client.get_server_time()
        print(f"✅ Temps serveur: {server_time['serverTime']}")
        
        # Test 3: Récupère la balance
        print("\n💰 Récupération des balances...")
        account = client.get_account()
        
        usdt_balance = 0
        btc_balance = 0
        
        for balance in account['balances']:
            if balance['asset'] == 'USDT':
                usdt_balance = float(balance['free'])
            elif balance['asset'] == 'BTC':
                btc_balance = float(balance['free'])
        
        print(f"   USDT: {usdt_balance:.2f}")
        print(f"   BTC: {btc_balance:.6f}")
        
        # Test 4: Récupère le prix BTC
        print("\n📊 Prix BTC/USDT:")
        ticker = client.get_symbol_ticker(symbol='BTCUSDT')
        price = float(ticker['price'])
        print(f"   ${price:,.2f}")
        
        # Test 5: Crée un ordre test (ne déplace pas de fonds)
        print("\n📝 Test de création d'ordre...")
        from binance.enums import SIDE_BUY, ORDER_TYPE_LIMIT
        
        test_order = client.create_test_order(
            symbol='BTCUSDT',
            side=SIDE_BUY,
            type=ORDER_TYPE_LIMIT,
            quantity=0.001,
            price=round(price * 0.9, 2)  # -10% du prix actuel
        )
        print("✅ Ordre test créé avec succès")
        
        print("\n" + "="*50)
        print("🎉 SUCCÈS! Tous les tests ont réussi!")
        print("="*50)
        print("\nTon environnement est prêt pour AUTOBOT.")
        print("Tu peux maintenant lancer le bot avec confiance.")
        
        return True
        
    except BinanceAPIException as e:
        print(f"\n❌ Erreur API Binance: {e}")
        print(f"   Code: {e.code}")
        print(f"   Message: {e.message}")
        
        if e.code == -2015:
            print("\n💡 Les clés API sont invalides ou expirées.")
            print("   Régénère de nouvelles clés sur testnet.binance.vision")
        elif e.code == -1021:
            print("\n💡 Problème de synchronisation horaire.")
            print("   Vérifie que ton PC a l'heure correcte.")
        
        return False
        
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        return False

def main():
    """Fonction principale"""
    print("="*50)
    print("🤖 AUTOBOT - Test Connexion Binance Testnet")
    print("="*50)
    
    # Vérifie l'installation
    if not check_installation():
        sys.exit(1)
    
    # Test la connexion
    if test_connection():
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
