"""
Kraken API Test Module - Tests de connexion et trading paper
"""

import logging
import os
import sys
from typing import Dict, Optional, Tuple
from decimal import Decimal
import time

# Ajoute src au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger(__name__)

# Constantes de sécurité
SAFETY_TEST_VOLUME = 0.0001  # Minimum BTC order; ~€8 at €80k/BTC
MIN_PRICE_SANITY_CHECK = 1000.0  # Prix minimum acceptable (€)
ORDER_RETRY_ATTEMPTS = 3
ORDER_RETRY_DELAY = 1.0  # secondes


class KrakenAPITester:
    """Testeur pour API Kraken - valide connexion, balance, ordres"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Args:
            api_key: Clé API Kraken (ou KRAKEN_API_KEY env var)
            api_secret: Secret API Kraken (ou KRAKEN_API_SECRET env var)
        """
        self.api_key = api_key or os.getenv('KRAKEN_API_KEY')
        self.api_secret = api_secret or os.getenv('KRAKEN_API_SECRET')
        
        self.client = None
        self.tests_passed = 0
        self.tests_failed = 0
        
    def _import_kraken(self):
        """Importe le client Kraken (crée dépendance optionnelle)"""
        try:
            import krakenex
            return krakenex.API(key=self.api_key, secret=self.api_secret)
        except ImportError:
            logger.error("❌ Module 'krakenex' non installé. Run: pip install krakenex")
            return None
        except Exception:
            logger.exception("❌ Erreur création client Kraken")
            return None
    
    def test_connection(self) -> bool:
        """Test 1: Connexion de base à l'API"""
        logger.info("🧪 Test 1: Connexion API Kraken...")
        
        self.client = self._import_kraken()
        if not self.client:
            self.tests_failed += 1
            return False
        
        try:
            # Test simple: récupère l'heure du serveur
            response = self.client.query_public('Time')
            if 'result' in response:
                server_time = response['result']['unixtime']
                logger.info(f"✅ Connexion OK - Serveur time: {server_time}")
                self.tests_passed += 1
                return True
            else:
                logger.error(f"❌ Erreur API: {response.get('error', 'Unknown')}")
                self.tests_failed += 1
                return False
        except Exception as e:
            logger.error(f"❌ Exception connexion: {e}")
            self.tests_failed += 1
            return False
    
    def test_balance(self) -> bool:
        """Test 2: Récupération du solde"""
        logger.info("🧪 Test 2: Récupération solde...")
        
        if not self.client:
            logger.error("❌ Client non initialisé")
            self.tests_failed += 1
            return False
        
        try:
            response = self.client.query_private('Balance')
            if 'result' in response:
                balances = response['result']
                
                # Affiche les balances non-nulles
                non_zero = {k: v for k, v in balances.items() if float(v) > 0}
                
                if non_zero:
                    logger.info(f"✅ Balance récupérée:")
                    for asset, amount in non_zero.items():
                        logger.info(f"   {asset}: {amount}")
                else:
                    logger.info("✅ Balance récupérée (tous les soldes sont à 0)")
                
                # Vérifie spécifiquement EUR et BTC
                eur = balances.get('ZEUR', '0')
                btc = balances.get('XXBT', '0')
                logger.info(f"   EUR: {eur}")
                logger.info(f"   BTC: {btc}")
                
                self.tests_passed += 1
                return True
            else:
                error = response.get('error', ['Unknown'])[0]
                if 'Invalid key' in error or 'Invalid signature' in error:
                    logger.error(f"❌ Clés API invalides: {error}")
                else:
                    logger.error(f"❌ Erreur balance: {error}")
                self.tests_failed += 1
                return False
        except Exception:
            logger.exception("❌ Exception balance")
            self.tests_failed += 1
            return False
    
    def test_ticker(self) -> bool:
        """Test 3: Récupération prix marché (XXBTZEUR)"""
        logger.info("🧪 Test 3: Récupération prix XXBTZEUR...")
        
        if not self.client:
            self.tests_failed += 1
            return False
        
        try:
            response = self.client.query_public('Ticker', {'pair': 'XXBTZEUR'})
            if 'result' in response:
                ticker = response['result']['XXBTZEUR']
                last_price = ticker['c'][0]  # Prix last trade
                high_24h = ticker['h'][1]     # High 24h
                low_24h = ticker['l'][1]      # Low 24h
                
                logger.info(f"✅ Ticker XXBTZEUR:")
                logger.info(f"   Last: {last_price} €")
                logger.info(f"   High 24h: {high_24h} €")
                logger.info(f"   Low 24h: {low_24h} €")
                
                self.tests_passed += 1
                return True
            else:
                logger.error(f"❌ Erreur ticker: {response.get('error', 'Unknown')}")
                self.tests_failed += 1
                return False
        except Exception:
            logger.exception("❌ Exception ticker")
            self.tests_failed += 1
            return False
    
    def test_paper_order(self) -> bool:
        """Test 4: Validation d'ordre (sans exécution réelle)"""
        logger.info("🧪 Test 4: Validation d'ordre (DRY-RUN - aucun ordre réel placé)...")
        
        if not self.client:
            self.tests_failed += 1
            return False
        
        try:
            # Récupère prix actuel
            ticker_resp = self.client.query_public('Ticker', {'pair': 'XXBTZEUR'})
            if 'result' not in ticker_resp:
                logger.error("❌ Impossible de récupérer le prix")
                self.tests_failed += 1
                return False
            
            current_price = float(ticker_resp['result']['XXBTZEUR']['c'][0])
            
            # CORRECTION: Sanity check sur le prix
            if current_price < MIN_PRICE_SANITY_CHECK:
                logger.error(f"❌ Prix anormal détecté: {current_price} (min attendu: {MIN_PRICE_SANITY_CHECK})")
                self.tests_failed += 1
                return False
            
            # Ordre LIMIT d'achat (pour validation uniquement)
            limit_price = round(current_price * 0.9, 1)
            volume = SAFETY_TEST_VOLUME
            
            logger.info(f"   Prix actuel: {current_price:.1f} €")
            logger.info(f"   Ordre LIMIT achat @ {limit_price:.1f} € ({volume} BTC)")
            logger.info(f"   🔒 Mode VALIDATE uniquement - AUCUN ordre réel ne sera placé")
            
            # CORRECTION: Utilise 'validate': True pour dry-run
            order_data = {
                'pair': 'XXBTZEUR',
                'type': 'buy',
                'ordertype': 'limit',
                'price': str(limit_price),
                'volume': str(volume),
                'validate': 'true'  # CORRECTION: Dry-run, pas d'ordre réel
            }
            
            response = self.client.query_private('AddOrder', order_data)
            
            if 'result' in response:
                # En mode validate, il n'y a pas de txid, juste la validation
                logger.info(f"✅ Ordre validé avec succès (DRY-RUN)")
                logger.info(f"   Détails: {response['result']}")
                self.tests_passed += 1
                return True
            else:
                error = response.get('error', ['Unknown'])
                if isinstance(error, list):
                    error = error[0]
                
                if 'Insufficient funds' in str(error):
                    logger.warning(f"⚠️ Fonds insuffisants pour l'ordre (normal si compte vide)")
                    logger.info("   ✅ L'API fonctionne, juste pas assez d'EUR")
                    self.tests_passed += 1
                    return True
                else:
                    logger.error(f"❌ Erreur validation ordre: {error}")
                    self.tests_failed += 1
                    return False
                    
        except Exception:
            logger.exception("❌ Exception ordre")
            self.tests_failed += 1
            return False
    
    def test_open_orders(self) -> bool:
        """Test 5: Récupération des ordres ouverts"""
        logger.info("🧪 Test 5: Récupération ordres ouverts...")
        
        if not self.client:
            self.tests_failed += 1
            return False
        
        try:
            response = self.client.query_private('OpenOrders')
            if 'result' in response:
                open_orders = response['result']['open']
                logger.info(f"✅ {len(open_orders)} ordre(s) ouvert(s)")
                self.tests_passed += 1
                return True
            else:
                logger.error(f"❌ Erreur: {response.get('error', 'Unknown')}")
                self.tests_failed += 1
                return False
        except Exception:
            logger.exception("❌ Exception")
            self.tests_failed += 1
            return False
    
    def cleanup(self):
        """Nettoyage: annule tous les ordres ouverts (sécurité)"""
        if not self.client:
            return
        
        try:
            logger.info("🧹 Nettoyage: vérification ordres ouverts...")
            response = self.client.query_private('OpenOrders')
            if 'result' in response:
                open_orders = response['result']['open']
                if open_orders:
                    logger.warning(f"⚠️ {len(open_orders)} ordre(s) ouvert(s) détecté(s) - annulation...")
                    for txid in open_orders.keys():
                        try:
                            self.client.query_private('CancelOrder', {'txid': txid})
                            logger.info(f"   Ordre {txid[:8]}... annulé")
                        except Exception:
                            logger.exception(f"   Erreur annulation {txid[:8]}...")
                else:
                    logger.info("✅ Aucun ordre ouvert")
        except Exception:
            logger.exception("❌ Erreur nettoyage")
    
    def run_all_tests(self) -> Tuple[int, int]:
        """Lance tous les tests et retourne (passed, failed)"""
        logger.info("="*60)
        logger.info("🚀 DÉMARRAGE DES TESTS API KRAKEN")
        logger.info("="*60)
        
        tests = [
            ("Connexion", self.test_connection),
            ("Balance", self.test_balance),
            ("Ticker", self.test_ticker),
            ("Ordre Paper", self.test_paper_order),
            ("Ordres Ouverts", self.test_open_orders),
        ]
        
        for name, test_func in tests:
            logger.info("")
            try:
                test_func()
            except Exception as e:
                logger.error(f"❌ Test '{name}' a crashé: {e}")
                self.tests_failed += 1
        
        logger.info("")
        logger.info("="*60)
        logger.info("📊 RÉSULTATS")
        logger.info("="*60)
        logger.info(f"✅ Réussis: {self.tests_passed}")
        logger.info(f"❌ Échoués: {self.tests_failed}")
        
        if self.tests_failed == 0:
            logger.info("🎉 TOUS LES TESTS ONT RÉUSSI!")
        elif self.tests_failed <= 1:
            logger.info("⚠️  Quelques échecs mineurs (peut-être normal)")
        else:
            logger.error("❌ Plusieurs échecs - vérifiez la configuration")
        
        return self.tests_passed, self.tests_failed


def main():
    """Point d'entrée pour les tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test API Kraken (DRY-RUN uniquement)')
    parser.add_argument('--api-key', help='Clé API Kraken (optionnel, utilise KRAKEN_API_KEY env var par défaut)')
    # CORRECTION: Retiré --api-secret pour éviter fuite dans bash_history/ps aux
    parser.add_argument('-v', '--verbose', action='store_true', help='Mode verbeux')
    
    args = parser.parse_args()
    
    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Vérifie les credentials
    # CORRECTION: api_secret UNIQUEMENT via env var (pas CLI)
    api_key = args.api_key or os.getenv('KRAKEN_API_KEY')
    api_secret = os.getenv('KRAKEN_API_SECRET')
    
    if not api_key or not api_secret:
        logger.error("❌ Clés API manquantes!")
        logger.error("")
        logger.error("Configuration requise (une des deux options):")
        logger.error("")
        logger.error("Option 1 - Variables d'environnement (RECOMMANDÉ):")
        logger.error("   export KRAKEN_API_KEY='votre_clé'")
        logger.error("   export KRAKEN_API_SECRET='votre_secret'")
        logger.error("   python test_kraken_api.py")
        logger.error("")
        logger.error("Option 2 - Clé en argument, secret en env:")
        logger.error("   export KRAKEN_API_SECRET='votre_secret'")
        logger.error("   python test_kraken_api.py --api-key 'votre_clé'")
        logger.error("")
        logger.error("⚠️  Note: Pour la sécurité, le secret n'est jamais accepté en argument.")
        sys.exit(1)
    
    # CORRECTION: Réduit l'exposition de la clé (4 premiers + 2 derniers caractères)
    masked_key = f"{api_key[:4]}...{api_key[-2:]}" if len(api_key) > 6 else "***"
    logger.info(f"🔑 API Key: {masked_key}")
    logger.info("🔒 Mode DRY-RUN: Aucun ordre réel ne sera placé")
    
    # Lance les tests avec cleanup garanti
    tester = None
    exit_code = 0
    try:
        tester = KrakenAPITester(api_key, api_secret)
        passed, failed = tester.run_all_tests()
        exit_code = 0 if failed == 0 else 1
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Interruption détectée")
        exit_code = 130
    except Exception:
        logger.exception("❌ Erreur fatale")
        exit_code = 1
    finally:
        if tester:
            tester.cleanup()
            
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
