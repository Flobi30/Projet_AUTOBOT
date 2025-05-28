Crée un test Pytest dans `tests/test_train_endpoint.py` :
- POST `/train`.  
- Vérifie `response.status_code == 200`.  
- Vérifie que la réponse JSON contient `"status": "training_started"` et `"job_id"` (str).
