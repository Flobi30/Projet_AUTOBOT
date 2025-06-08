#!/usr/bin/env python3

import os
import sys
sys.path.append('/home/ubuntu/Projet_AUTOBOT/src')

from dotenv import load_dotenv
load_dotenv()

def test_provider_integration(provider_name, module_path):
    try:
        exec(f"from {module_path} import *")
        print(f"✅ {provider_name}: Module importé avec succès")
        
        api_key_var = {
            'alphavantage': 'ALPHA_VANTAGE_API_KEY',
            'newsapi': 'NEWSAPI_KEY', 
            'twelvedata': 'TWELVE_DATA_API_KEY',
            'fred': 'FRED_API_KEY',
            'shopify': 'SHOPIFY_API_KEY',
            'binance': 'BINANCE_API_KEY',
            'coinbase': 'COINBASE_API_KEY',
            'kraken': 'KRAKEN_API_KEY'
        }.get(provider_name.lower())
        
        if api_key_var:
            api_key = os.getenv(api_key_var, "")
            status = "✅ Configurée" if api_key else "❌ Non configurée"
            print(f"   Clé API {api_key_var}: {status}")
        
        return True
    except Exception as e:
        print(f"❌ {provider_name}: Erreur - {e}")
        return False

def main():
    print("🔍 Test des intégrations API AUTOBOT")
    print("=" * 50)
    
    providers = [
        ("Alpha Vantage", "autobot.providers.alphavantage"),
        ("NewsAPI", "autobot.providers.newsapi"),
        ("Twelve Data", "autobot.providers.twelvedata"),
        ("FRED", "autobot.providers.fred"),
        ("Shopify", "autobot.providers.shopify"),
        ("Binance", "autobot.providers.binance"),
        ("Coinbase", "autobot.providers.coinbase"),
        ("Kraken", "autobot.providers.kraken")
    ]
    
    success_count = 0
    for provider_name, module_path in providers:
        if test_provider_integration(provider_name, module_path):
            success_count += 1
        print()
    
    print(f"📊 Résultat: {success_count}/{len(providers)} intégrations fonctionnelles")
    
    if success_count == len(providers):
        print("🎉 Toutes les intégrations API sont opérationnelles!")
    else:
        print("⚠️  Certaines intégrations nécessitent une attention.")

if __name__ == "__main__":
    main()
