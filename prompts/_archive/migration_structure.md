# Reorganisation automatique du projet Projet_AUTOBOT

## Contexte
- Objectif : système autonome de trading + e‑commerce, code déjà généré par GPT‑Code/OpenInterpreter.
- Doit rester : tout ce qui est code applicatif (modules Python), tests, CI/CD, déploiement, documentation.
- Doit être archivé (déplacé dans `archive/`) : stubs vides, scaffolds anciens, logs, backups, dossiers temporaires, anciens artefacts.

## Règles
1. **Conserver** à la racine :
   - Dossiers : `src/`, `tests/`, `scripts/`, `.github/`, `k8s/`, `docs/`, `prompts/`
   - Fichiers essentiels : `setup.py`, `Dockerfile`, `docker-compose.yml`, `requirements*.txt`, `README.md`, `pyproject.toml`
2. **Tout le code Python** (.py et packages avec `__init__.py`) en dehors de `src/` doit être **déplacé** sous `src/autobot/` en gardant leur nom.
3. **Archiver** dans `archive/` _tout le reste_ (logs, anciens scaffolds, backups, dossiers `__pycache__`, `.pytest_cache`, etc.).
4. Le script doit être **idempotent** (si relancé, ne rien redéplacer deux fois).

## Tâche
Génère un script Python `scripts/organize_project.py` qui :
- Applique ces règles automatiquement.
- Journalise : pour chaque déplacement, afficher “Moved X → Y” ou “Archived Z”.
- Créer les dossiers cibles s’ils n’existent pas.
- Ne demande aucune intervention manuelle.

