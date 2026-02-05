# Configuration API Kraken pour AUTOBOT

## Pourquoi Kraken ?

- **Pas de géoblocage** : Accessible depuis tous les serveurs (contrairement à Binance)
- **API stable** : Documentation claire et endpoints fiables
- **Idéal pour Grid Trading** : Frais compétitifs et bonne liquidité sur BTC/EUR

## Création des clés API Kraken

### Étape 1 : Connexion à Kraken
1. Allez sur [https://www.kraken.com](https://www.kraken.com)
2. Connectez-vous à votre compte (ou créez-en un)

### Étape 2 : Accéder aux paramètres API
1. Cliquez sur votre profil en haut à droite
2. Sélectionnez **Security** > **API**
3. Ou accédez directement à : [https://www.kraken.com/u/security/api](https://www.kraken.com/u/security/api)

### Étape 3 : Créer une nouvelle clé API
1. Cliquez sur **Add key** ou **Generate new key**
2. Donnez un nom descriptif (ex: "AUTOBOT Trading")
3. Sélectionnez les permissions nécessaires :

#### Permissions minimales (lecture seule) :
- ✅ **Query Funds** - Pour voir les balances

#### Permissions pour le trading :
- ✅ **Query Funds** - Pour voir les balances
- ✅ **Query Open Orders & Trades** - Pour voir les ordres
- ✅ **Query Closed Orders & Trades** - Pour l'historique
- ✅ **Create & Modify Orders** - Pour passer des ordres
- ✅ **Cancel/Close Orders** - Pour annuler des ordres

### Étape 4 : Sécurité (recommandé)
- Activez la restriction par IP si possible
- N'activez **jamais** les permissions de retrait pour un bot de trading

### Étape 5 : Sauvegarder les clés
1. Copiez la **API Key** (clé publique)
2. Copiez la **Private Key** (clé secrète) - **Elle ne sera affichée qu'une seule fois !**

## Configuration dans AUTOBOT

### Option 1 : Variables d'environnement (recommandé)
```bash
export KRAKEN_API_KEY="votre_cle_api"
export KRAKEN_API_SECRET="votre_cle_privee"
```

### Option 2 : Fichier .env
Créez ou modifiez le fichier `.env` à la racine du projet :
```
KRAKEN_API_KEY=votre_cle_api
KRAKEN_API_SECRET=votre_cle_privee
```

## Test de connexion

Exécutez le script de test :
```bash
cd /chemin/vers/Projet_AUTOBOT
source .env  # Si vous utilisez un fichier .env
python scripts/kraken_connect.py
```

### Résultat attendu :
```
[2024-XX-XX...] Connexion à Kraken...
[CONNECT] Kraken OK
[BALANCE] EUR: X.XX, BTC: X.XXXXXXXX
[STATUS] Connexion opérationnelle
[MARKET] BTC/EUR: XXXXX.XX EUR
```

## Symboles Kraken

| Symbole Kraken | Paire    |
|----------------|----------|
| XXBTZEUR       | BTC/EUR  |
| XETHZEUR       | ETH/EUR  |
| XXBTZUSD       | BTC/USD  |
| XETHZUSD       | ETH/USD  |

## Différences avec Binance

| Aspect           | Kraken                    | Binance                |
|------------------|---------------------------|------------------------|
| Géoblocage       | Non                       | Oui (certains pays)    |
| Symboles         | XXBTZEUR                  | BTCUSDT                |
| Testnet          | Non disponible            | Disponible             |
| Frais            | 0.16% - 0.26%             | 0.1%                   |
| Fiat             | EUR, USD, GBP...          | Limité                 |

## Dépannage

### Erreur "Invalid key"
- Vérifiez que vous avez copié la clé complète
- La clé privée Kraken est longue (base64)

### Erreur "Permission denied"
- Vérifiez les permissions de votre clé API
- Assurez-vous que "Query Funds" est activé

### Erreur de connexion
- Vérifiez votre connexion internet
- Kraken peut avoir des maintenances planifiées

## Ressources

- [Documentation API Kraken](https://docs.kraken.com/rest/)
- [Status Kraken](https://status.kraken.com/)
- [Support Kraken](https://support.kraken.com/)
