# Tests AUTOBOT V2

## Tests API Kraken

Le fichier `test_kraken_api.py` permet de valider la connexion à l'API Kraken en **mode DRY-RUN uniquement** (aucun ordre réel placé).

### 🔒 Sécurité

- **Aucun ordre réel** n'est jamais placé sur le marché
- Les tests utilisent le flag `validate=True` de l'API Kraken
- Le secret API n'est accepté **que** via variables d'environnement (jamais en ligne de commande)

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

Puis lancez :
```bash
python src/autobot/v2/tests/test_kraken_api.py
```

Alternative (clé en argument, secret en env) :
```bash
export KRAKEN_API_SECRET="votre_secret"
python src/autobot/v2/tests/test_kraken_api.py --api-key "votre_clé"
```

⚠️ **Pour la sécurité**, `--api-secret` n'est PAS supporté (évite la fuite dans bash_history).

### Exécution des tests

```bash
# Mode normal
python src/autobot/v2/tests/test_kraken_api.py

# Mode verbeux (plus de détails)
python src/autobot/v2/tests/test_kraken_api.py -v

# Avec le script
./src/autobot/v2/tests/test-kraken.sh
```

### Ce qui est testé

1. ✅ **Connexion API** - Vérifie que l'API répond
2. ✅ **Balance** - Récupère les soldes (EUR, BTC)
3. ✅ **Ticker** - Récupère le prix XXBTZEUR
4. ✅ **Validation d'ordre** - Valide un ordre sans l'exécuter (DRY-RUN)
5. ✅ **Ordres Ouverts** - Liste les ordres en cours

### 🔒 Mode DRY-RUN (Test 4)

Le test 4 utilise le paramètre `validate=True` de l'API Kraken :
- L'API valide la signature, les fonds, le format
- **Aucun ordre n'est placé sur le marché**
- Pas besoin d'annulation
- 100% safe

### Résultats attendus

```
🔒 Mode DRY-RUN: Aucun ordre réel ne sera placé
✅ Réussis: 5
❌ Échoués: 0
🎉 TOUS LES TESTS ONT RÉUSSI!
```

Si vous avez des échecs :
- Vérifiez vos clés API
- Vérifiez que votre compte Kraken est actif
- Vérifiez votre connexion Internet
