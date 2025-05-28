Crée un test Pytest dans `tests/test_logs_endpoint.py` :
- GET `/logs`.  
- Vérifie `response.status_code == 200`.  
- Vérifie que la réponse JSON est une liste non vide d’objets contenant `"timestamp"`, `"level"`, `"msg"`.
