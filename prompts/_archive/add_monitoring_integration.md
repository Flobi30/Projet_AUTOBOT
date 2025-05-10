Dans src/autobot/guardian.py :
- Ajoute une fonction `get_metrics()` qui :
  1. Lit ou calcule les métriques système (CPU, mémoire, latence des endpoints).
  2. Retourne un dict JSON.
Dans `src/autobot/router.py`, crée un nouvel endpoint GET `/monitoring` qui :
  1. Appelle `get_metrics()`.
  2. Retourne la réponse JSON.
Ajoute un commentaire `# REAL_MONITORING`.
