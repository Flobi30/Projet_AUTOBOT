# check_outputs.py

import json, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('prompts/prompts_index.json', 'r', encoding='utf-8') as f:
    prompts = json.load(f)

total_ok = total_missing = 0

for entry in prompts:
    p = entry['prompt']
    for out in entry.get('outputs', []):
        exists = os.path.exists(out)
        status = 'OK' if exists else 'MISSING'
        if exists:
            total_ok += 1
        else:
            total_missing += 1
        print(f"{p:25s} -> {out:40s} {status}")

print()
print("Résumé :", total_ok, "fichiers générés,", total_missing, "manquants.")

