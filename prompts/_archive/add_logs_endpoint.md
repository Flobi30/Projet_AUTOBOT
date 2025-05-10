Dans src/autobot/router.py :
Ajoute un endpoint FastAPI GET `/logs` qui renvoie les derniers logs collectés par `autobot_guardian` au format JSON, par exemple :
```json
[
  { "timestamp": "2025-05-08T12:34:56Z", "level": "INFO", "msg": "Backtest completed" },
  …
]
```
Ajoute un commentaire unique `# BASELINE_LOGS`.
