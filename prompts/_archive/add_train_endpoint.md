Dans src/autobot/router.py :
Ajoute un endpoint FastAPI POST `/train` qui déclenche (placeholder) l’entraînement RL.
Il ne prend pas de body et renvoie :
```json
{ "status": "training_started", "job_id": "abc123" }
```
Ajoute un commentaire unique `# BASELINE_TRAIN`.
