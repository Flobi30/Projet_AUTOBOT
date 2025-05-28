## System
You are an orchestration engine.
## User
Écris `scripts/generate_all.py` qui :
1. Lit tous les prompts dans `prompts/_archive/`.
2. Lance GPT-Code sur chacun en parallèle (multiprocessing ou asyncio).
3. Logue les succès/échecs dans `generation_log.json`.
4. Attend la fin de tous et sort.
## Output
- `scripts/generate_all.py`
