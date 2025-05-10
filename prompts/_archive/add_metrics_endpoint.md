Dans src/autobot/router.py :
Ajoute un endpoint FastAPI GET `/metrics` qui renvoie un dict JSON de KPI e-commerce fictifs :
```json
{
  "total_sales": 12345.67,
  "conversion_rate": 2.34,
  "avg_order_value": 78.90
}
```
Ajoute un commentaire unique `# BASELINE_METRICS`.
