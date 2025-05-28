Dans src/autobot/rl/train.py :
- Expose une fonction `start_training()` qui :
  1. Charge l’environnement et les hyperparamètres (placeholder).
  2. Lance `RLModule.train()` (importé depuis `src/autobot/rl`).
  3. Retourne un `job_id` unique (uuid4).
- Dans `src/autobot/router.py`, modifie l’endpoint POST `/train` pour qu’il :
  1. Appelle `start_training()`.
  2. Retourne `{ "status": "training_started", "job_id": job_id }`.
Ajoute un commentaire `# REAL_RL_TRAIN`.
