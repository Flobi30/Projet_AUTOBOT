Crée un test Pytest dans `tests/test_backtest_endpoint.py` :
- Utilise la fixture `client` de `tests/conftest.py`.  
- Envoie un POST `/backtest` avec `{ "strategy": "x", "parameters": {} }`.  
- Vérifie `response.status_code == 200`.  
- Vérifie que la réponse JSON contient les champs `"strategy"` (str) et `"metrics"` (dict de float).
