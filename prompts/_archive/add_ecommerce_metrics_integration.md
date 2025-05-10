Dans src/autobot/ecommerce/kpis.py :
- Vérifie que la fonction `get_kpis()` existe et retourne un dict de floats.
- Si nécessaire, crée-la pour appeler Shopify ou un stub interne.
Dans `src/autobot/router.py`, modifie l’endpoint GET `/metrics` pour qu’il :
  1. Importe et appelle `from autobot.ecommerce.kpis import get_kpis`.
  2. Retourne directement `get_kpis()` au lieu du dict simulé.
Ajoute un commentaire `# REAL_ECOM_KPIS`.
