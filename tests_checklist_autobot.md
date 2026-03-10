# 📋 CHECKLIST VALIDATION - Bot Grid Trading

## 10 Points pour valider qu'un bot fonctionne VRAIMENT

### 1. Connexion API ✅
- [ ] Le bot se connecte à Binance Testnet (pas de mocks)
- [ ] La connexion est stable (pas de timeout immédiat)
- [ ] Les clés API sont valides et reconnues

### 2. Récupération Données ✅
- [ ] Le bot récupère le prix BTC/USDT en temps réel
- [ ] Le prix est cohérent (+- 5% du marché réel)
- [ ] Les données se mettent à jour (pas figées)

### 3. Calcul Grid ✅
- [ ] Les 15 niveaux sont calculés correctement
- [ ] La fourchette (+/- 7%) est respectée
- [ ] Le capital est divisé équitablement (33€/niveau)

### 4. Placement Ordre Achat ✅
- [ ] Un ordre d'achat est créé sur le niveau le plus bas
- [ ] L'ordre apparaît dans Binance (visible sur l'interface)
- [ ] Les paramètres sont corrects (prix, quantité)

### 5. Gestion du Fill ✅
- [ ] Le bot détecte quand l'ordre est exécuté (fill)
- [ ] Le temps de détection est < 10 secondes
- [ ] Les infos du fill sont correctement enregistrées

### 6. Placement Ordre Vente ✅
- [ ] Un ordre de vente est créé automatiquement après l'achat
- [ ] Le prix de vente inclut la marge (0.8%)
- [ ] L'ordre est actif sur Binance

### 7. Gestion des Erreurs ✅
- [ ] Si déconnexion, le bot tente de reconnecter
- [ ] Si erreur API, le bot log l'erreur clairement
- [ ] Le bot ne crash pas sur une erreur temporaire

### 8. Logging ✅
- [ ] Chaque action est loguée (connexion, ordre, fill, erreur)
- [ ] Les logs sont horodatés
- [ ] On peut suivre le flux complet dans les logs

### 9. Sécurité ✅
- [ ] Pas de clés API en dur dans le code
- [ ] Pas de données sensibles dans les logs
- [ ] Vérification des paramètres avant ordre

### 10. Documentation ✅
- [ ] Instructions claires pour reproduire
- [ ] Liste des dépendances
- [ ] Explication du fonctionnement

---

## 🐍 Template Test Python (pytest)

```python
"""Tests d'intégration pour AUTOBOT Grid Trading"""
import pytest
import os
from dotenv import load_dotenv

# Charger variables d'environnement
load_dotenv()

class TestBinanceConnection:
    """Test 1: Connexion API"""
    
    def test_connection_with_real_api(self):
        """Vérifie qu'on peut se connecter avec de vraies clés"""
        from binance.client import Client
        
        client = Client(
            api_key=os.getenv('BINANCE_TESTNET_API_KEY'),
            api_secret=os.getenv('BINANCE_TESTNET_API_SECRET'),
            testnet=True
        )
        
        # Test: récupération balance
        balance = client.get_asset_balance(asset='USDT')
        assert balance is not None
        assert 'free' in balance
        print(f"✅ Connecté! Balance USDT: {balance['free']}")
    
    def test_connection_fails_with_wrong_keys(self):
        """Vérifie que mauvaises clés = échec"""
        from binance.client import Client
        from binance.exceptions import BinanceAPIException
        
        client = Client(api_key='fake', api_secret='fake', testnet=True)
        
        with pytest.raises(BinanceAPIException):
            client.get_account()


class TestPriceFetching:
    """Test 2: Récupération prix"""
    
    def test_get_btc_price(self):
        """Vérifie qu'on récupère le prix BTC/USDT"""
        from binance.client import Client
        
        client = Client(
            api_key=os.getenv('BINANCE_TESTNET_API_KEY'),
            api_secret=os.getenv('BINANCE_TESTNET_API_SECRET'),
            testnet=True
        )
        
        ticker = client.get_symbol_ticker(symbol='BTCUSDT')
        price = float(ticker['price'])
        
        # Vérification: prix cohérent (BTC entre 20k et 200k)
        assert 20000 < price < 200000
        print(f"✅ Prix BTC: ${price:,.2f}")


class TestGridCalculation:
    """Test 3: Calcul niveaux Grid"""
    
    def test_grid_levels_calculation(self):
        """Vérifie calcul des 15 niveaux"""
        # Exemple de fonction à implémenter
        def calculate_grid_levels(center_price, range_percent=14, num_levels=15):
            half_range = range_percent / 2 / 100
            lower = center_price * (1 - half_range)
            upper = center_price * (1 + half_range)
            step = (upper - lower) / (num_levels - 1)
            return [lower + i * step for i in range(num_levels)]
        
        levels = calculate_grid_levels(50000)
        
        assert len(levels) == 15
        assert levels[0] < 50000  # Premier niveau < prix centre
        assert levels[-1] > 50000  # Dernier niveau > prix centre
        assert levels[7] == pytest.approx(50000, rel=0.01)  # Milieu ~ centre


class TestOrderPlacement:
    """Test 4 & 5: Placement et gestion ordres"""
    
    def test_place_buy_order(self):
        """Vérifie qu'on peut placer un ordre d'achat"""
        from binance.client import Client
        from binance.enums import ORDER_TYPE_LIMIT, SIDE_BUY
        
        client = Client(
            api_key=os.getenv('BINANCE_TESTNET_API_KEY'),
            api_secret=os.getenv('BINANCE_TESTNET_API_SECRET'),
            testnet=True
        )
        
        # Ordre LIMIT à prix très bas (ne sera pas fillé tout de suite)
        order = client.create_test_order(
            symbol='BTCUSDT',
            side=SIDE_BUY,
            type=ORDER_TYPE_LIMIT,
            quantity=0.001,
            price=10000  # Prix très bas pour test
        )
        
        assert order is not None
        print(f"✅ Ordre test créé: {order}")


class TestErrorHandling:
    """Test 7: Gestion erreurs"""
    
    def test_handles_network_error(self):
        """Vérifie gestion déconnexion réseau"""
        # À implémenter selon votre code
        pass
    
    def test_handles_api_error(self):
        """Vérifie gestion erreur API"""
        # À implémenter selon votre code
        pass


# Critère minimum pour dire "c'est fonctionnel"
MINIMUM_CRITERIA = {
    "connexion": "Se connecte à Binance Testnet sans erreur",
    "prix": "Récupère le prix BTC en temps réel",
    "grid": "Calcule 15 niveaux cohérents",
    "ordre": "Place un ordre qui apparaît sur Binance",
    "logs": "Log chaque étape clairement"
}

if __name__ == "__main__":
    print("🧪 Tests AUTOBOT Grid Trading")
    print("=" * 50)
    print("\nCritères minimums:")
    for key, desc in MINIMUM_CRITERIA.items():
        print(f"  ✅ {key}: {desc}")
    print("\nLancer: pytest test_grid_integration.py -v")
```

---

## ✅ Critères Minimums pour "C'est Fonctionnel"

Un bot Grid Trading est fonctionnel quand :

1. **Il se connecte** à Binance Testnet (pas de simulation)
2. **Il récupère** le prix BTC en temps réel
3. **Il calcule** 15 niveaux cohérents (+/- 7%)
4. **Il place** un ordre qui apparaît sur l'interface Binance
5. **Il gère** les erreurs sans crasher
6. **Il logue** chaque action pour pouvoir debug

**Si ces 6 points sont OK → Le bot est fonctionnel.**
