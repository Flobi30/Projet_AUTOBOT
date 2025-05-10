#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil

def main():
    # 1) Supprimer les anciens dossiers obsolètes (s’ils existent)
    for d in ['arbitrage', 'trading', 'ecommerce', 'simulator', 'dev_output', 'build', 'dist']:
        if os.path.isdir(d):
            shutil.rmtree(d)
            print(f"🗑️  Supprimé : {d}")

    # 2) Créer tous les dossiers nécessaires
    dirs = [
        'config', 'logs', 'backend', 'autoupdate', 'autoguardian',
        'modules/trading', 'modules/arbitrage', 'modules/ecommerce',
        'modules/simulator', 'modules/diversification',
        'AI_agents', 'utils', 'data/backtests',
        'frontend/templates', 'frontend/static/css', 'frontend/static/js',
        'autobot_integrations', 'deployment', 'tests', '.github/workflows'
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"✅ Créé : {d}")

    # 3) Créer (ou remplacer) le .env.template
    env = os.path.join('config', '.env.template')
    with open(env, 'w', encoding='utf-8') as f:
        f.write(
            "# CONFIGURATION ENVIRONNEMENT\n"
            "ENV=prod\n"
            "BINANCE_API=\n"
            "BACKTEST_INSTANCES=10\n"
            "MASTER_AUTH_KEY=\n"
        )
    print(f"✅ (Re)créé : {env}\n")

    print("✨ Structure du projet initialisée ! Lance maintenant `git add . && git commit -m \"Init structure\"`")

if __name__ == "__main__":
    main()

