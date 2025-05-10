Met à jour le Dockerfile du projet Autobot (base python:3.10-slim) pour :
1. Installer les dépendances de production et de développement (requirements.txt & requirements.dev.txt).
2. Exposer le port 8000.
3. Lancer l’application FastAPI avec Uvicorn via la commande :
```bash
CMD ["uvicorn", "autobot.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
Ajoute un commentaire unique `# BASELINE_DOCKERFILE`.
