#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# scripts/generate_all.py

"""
Orchestre la génération de tous les modules à partir des prompts Markdown,
en utilisant directement l’API Python d’Open Interpreter pour éviter les erreurs CLI,
et journalise les sorties dans prompts/generation_run.log.
"""

import os
import sys
import json
import time
import logging
from pathlib import Path

# Import de l’API Python d’Open Interpreter
from interpreter import interpreter

# ─── Environnement ──────────────────────────────────────────────────────────────
os.environ['PYTHONUTF8']    = '1'
os.environ['NO_COLOR']      = '1'
os.environ['RICH_NO_COLOR'] = '1'

# ─── Logging dans fichier uniquement ─────────────────────────────────────────────
LOG_PATH = 'prompts/generation_run.log'
if os.path.exists(LOG_PATH):
    for h in logging.getLogger().handlers:
        h.close()
        logging.getLogger().removeHandler(h)
    os.remove(LOG_PATH)
logging.basicConfig(
    filename=LOG_PATH,
    filemode='a',
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.DEBUG
)

# ─── Configuration de l’interpréteur LLM ─────────────────────────────────────────
# Forcer le modèle nano
interpreter.llm.model = os.getenv('AUTOBOT_MODEL', 'openai/gpt-4.1-nano-2025-04-14')

# ─── Constantes ─────────────────────────────────────────────────────────────────
INDEX_PATH      = 'prompts/prompts_index.json'
ARCHIVE_DIR     = 'prompts/_archive'
MAX_RETRIES     = 3
INITIAL_BACKOFF = 30   # secondes
MIN_FILE_SIZE   = 10   # bytes

# ─── Utilitaires ───────────────────────────────────────────────────────────────
def log(msg: str, level=logging.INFO):
    """Écrit un message horodaté dans le log file."""
    logging.log(level, msg)

def execute_prompt(md_path: str) -> str:
    """Exécute le prompt via l’API Python d’Open Interpreter et renvoie la réponse."""
    prompt = Path(md_path).read_text(encoding="utf-8", errors="replace")
    # envoie en une seule requête, sans streaming
    response = interpreter.chat(prompt, stream=False)
    # retourne le contenu du dernier message de l’assistant
    return response[-1].content

def output_valid(path: str) -> bool:
    """Vérifie qu’un fichier ou dossier de sortie est valide (taille min ou non vide)."""
    if not os.path.exists(path):
        return False
    if os.path.isfile(path):
        return os.path.getsize(path) > MIN_FILE_SIZE
    return any(name != '__init__.py' for name in os.listdir(path))

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    log('=== Début génération batch ===')
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        prompts = json.load(f)

    total = len(prompts)
    for i, entry in enumerate(prompts, start=1):
        name = entry.get('prompt', '<sans-nom>')
        log(f'[{i}/{total}] Vérif : {name}')

        outputs = entry.get('outputs', [])
        if outputs and all(output_valid(o) for o in outputs):
            log(f'[{i}/{total}] Skip (valide) : {name}')
            continue

        md_file = os.path.join(ARCHIVE_DIR, name)
        if not os.path.isfile(md_file):
            log(f'[{i}/{total}] Prompt manquant : {md_file}', logging.WARNING)
            continue

        log(f'[{i}/{total}] Exécution : {name}')
        retries, backoff = 0, INITIAL_BACKOFF
        while True:
            try:
                result_text = execute_prompt(md_file)
                log(f'[{i}/{total}] Succès : {name}')
                log('--- OUTPUT ---\n' + result_text, logging.DEBUG)
                break
            except Exception as e:
                if retries < MAX_RETRIES:
                    log(f'  Exception \"{e}\", retry {retries+1}/{MAX_RETRIES} après {backoff}s', logging.WARNING)
                    time.sleep(backoff)
                    retries += 1
                    backoff *= 2
                    continue
                else:
                    log(f'[{i}/{total}] Erreur fatale : {e}', logging.ERROR)
                    break

        log('---')
        time.sleep(5)

    log('=== Fin génération batch ===')

if __name__ == '__main__':
    main()

