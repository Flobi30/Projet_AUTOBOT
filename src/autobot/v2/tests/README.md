# Tests AUTOBOT V2

## Tests API Kraken

Le fichier `test_kraken_api.py` permet de valider la connexion à l'API Kraken sans risquer de perdre d'argent.

### Prérequis

```bash
pip install krakenex
```

Ou si vous avez un requirements.txt :
```bash
pip install -r requirements.txt
```

### Configuration

Définissez vos clés API Kraken via les variables d'environnement :

```bash
export KRAKEN_API_KEY="votre_clé"
export KRAKEN_API_SECRET="votre_secret"
```

Ou passez-les en arguments :
```bash
python src/autobot/v2/tests/test_kraken_api.py --api-key XXX --api-secret YYY
```

### Exécution des tests

```bash
# Mode normal
python src/autobot/v2/tests/test_kraken_api.py

# Mode verbeux (plus de détails)
python src/autobot/v2/tests/test_kraken_api.py -v
```

### Ce qui est testé

1. ✅ **Connexion API** - Vérifie que l'API répond
2. ✅ **Balance** - Récupère les soldes (EUR, BTC)
3. ✅ **Ticker** - Récupère le prix XXBTZEUR
4. ✅ **Ordre Paper** - Crée et annule un ordre LIMIT (loin du prix, pas d'exécution)
5. ✅ **Ordres Ouverts** - Liste les ordres en cours

### ⚠️ Important

- Le test 4 crée un ordre LIMIT d'achat à -10% du prix actuel (il ne sera pas exécuté)
- L'ordre est annulé immédiatement après création
- Si vous n'avez pas d'EUR, le test échouera avec "Insufficient funds" (c'est normal)

### Résultats attendus

```
✅ Réussis: 5
❌ Échoués: 0
🎉 TOUS LES TESTS ONT RÉUSSI!
```

Si vous avez des échecs :
- Vérifiez vos clés API
- Vérifiez que votre compte Kraken est actif
- Vérifiez votre connexion Internet
