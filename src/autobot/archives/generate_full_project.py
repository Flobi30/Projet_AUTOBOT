#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil


def generate_full_project():
    # 1) Supprimer les dossiers obsolètes
    for d in ['arbitrage','trading','ecommerce','simulator','dev_output','build','dist']:
        if os.path.isdir(d):
            shutil.rmtree(d)
    # 2) Créer l'arborescence cible
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
    # 3) .env.template
    with open('config/.env.template', 'w', encoding='utf-8') as f:
        f.write(
            "# CONFIGURATION ENVIRONNEMENT\n"
            "ENV=prod\n"
            "BINANCE_API=\n"
            "BACKTEST_INSTANCES=10\n"
            "MASTER_AUTH_KEY=\n"
        )

if __name__ == '__main__':
    generate_full_project()

