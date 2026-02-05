# Configuration Binance Testnet - AUTOBOT

## Etape 1: Creer un compte Binance Testnet

1. Allez sur https://testnet.binance.vision/
2. Cliquez sur "Log In with GitHub" (authentification via GitHub requise)
3. Autorisez l'application Binance Testnet

## Etape 2: Generer les cles API

1. Une fois connecte, cliquez sur "Generate HMAC_SHA256 Key"
2. Copiez les deux valeurs:
   - **API Key**: Votre cle publique
   - **Secret Key**: Votre cle secrete (ne sera plus visible apres)

## Etape 3: Configurer les variables d'environnement

Creez un fichier `.env` a la racine du projet:

```bash
cp .env.example .env
```

Editez le fichier `.env` et ajoutez vos cles:

```
BINANCE_TESTNET_API_KEY=votre_api_key_ici
BINANCE_TESTNET_API_SECRET=votre_secret_key_ici
```

## Etape 4: Tester la connexion

```bash
# Charger les variables d'environnement
source .env 2>/dev/null || export $(cat .env | xargs)

# Executer le script de test
python scripts/binance_testnet_connect.py
```

## Resultat attendu

```
[CONNECT] Binance Testnet OK
[BALANCE] USDT: 10000.00, BTC: 1.00000000
[STATUS] Connexion operationnelle
```

## Notes importantes

- Les cles Testnet sont **gratuites** et utilisent des fonds fictifs
- Le Testnet Binance fournit automatiquement des balances de test
- Les cles peuvent expirer - regenerez-les si necessaire
- Ne partagez JAMAIS vos cles API (meme Testnet)

## Depannage

| Erreur | Solution |
|--------|----------|
| `AuthenticationError` | Verifiez que les cles sont correctes et non expirees |
| `NetworkError` | Verifiez votre connexion internet |
| `Variables requises` | Assurez-vous que `.env` est charge |
