#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# scripts/organize_project.py

"""
Réorganise entièrement le dossier Projet_AUTOBOT :
- Crée la structure standard sous src/autobot/
- Déplace chaque fichier et dossier Python (module, package) vers src/autobot/
- Conserve les dossiers de configuration (k8s, .github, docs, prompts, tests, scripts)
- Place tout le reste dans archive/
Le script est idempotent : relance sans effet secondaire.
"""

import os
import shutil
from pathlib import Path

# Racine du projet (deux niveaux au-dessus de ce script)
ROOT = Path(__file__).resolve().parent.parent
# Cibles
SRC_AUTOBOT = ROOT / 'src' / 'autobot'
KEEP = {
    'setup.py', 'pyproject.toml', 'requirements.txt', 'requirements.dev.txt',
    'Dockerfile', 'docker-compose.yml',
    '.github', 'k8s', 'docs', 'prompts', 'tests', 'scripts', 'src', 'archive', 'static'
}
# Créer src/autobot
SRC_AUTOBOT.mkdir(parents=True, exist_ok=True)

# Fonction utilitaire de déplacement idempotent
def move_item(src: Path, dest: Path):
    if not src.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    # éviter déplacement vers soi-même
    if src.resolve() == dest.resolve():
        return
    # si cible existe déjà, on écrase
    if dest.exists():
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    shutil.move(str(src), str(dest))
    print(f"Moved {src.relative_to(ROOT)} → {dest.relative_to(ROOT)}")

# 1. Déplacer les .py à la racine (sauf setup.py)
for py in ROOT.glob('*.py'):
    if py.name != 'setup.py':
        move_item(py, SRC_AUTOBOT / py.name)

# 2. Déplacer les dossiers Python (packages) à la racine non dans KEEP
for d in ROOT.iterdir():
    if d.is_dir() and d.name not in KEEP:
        # si dossier contient .py ou __init__.py, c'est un package à migrer
        if any(d.glob('*.py')) or any((d / '__init__.py').exists() for _ in [0]):
            move_item(d, SRC_AUTOBOT / d.name)

# 3. Déplacer tout ce qui reste (hors KEEP) dans archive/
ARCHIVE = ROOT / 'archive'
ARCHIVE.mkdir(exist_ok=True)
for item in ROOT.iterdir():
    if item.name not in KEEP:
        move_item(item, ARCHIVE / item.name)

print("\nRéorganisation terminée. Vérifiez 'src/autobot/' et 'archive/'.")

