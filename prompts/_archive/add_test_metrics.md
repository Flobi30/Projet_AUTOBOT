Crée un test Pytest dans `tests/test_metrics_endpoint.py` :
- GET `/metrics`.  
- Vérifie `response.status_code == 200`.  
- Vérifie que la réponse JSON est un dict contenant les clés `"total_sales"`, `"conversion_rate"`, `"avg_order_value"` (valeurs numériques).
