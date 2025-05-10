#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

def generate_backend():
    backend_dir = 'backend'
    os.makedirs(backend_dir, exist_ok=True)

    files_content = {
        'loader.py': '''import os
from dotenv import load_dotenv

def load_config(env_path=None) -> dict:
    """
    Charge les variables d'environnement depuis config/.env ou env_path.
    Retourne un dict avec les paramètres essentiels.
    """
    env_file = env_path or os.path.join("config", ".env")
    load_dotenv(env_file)

    return {
        "ENV": os.getenv("ENV", "prod"),
        "BINANCE_API": os.getenv("BINANCE_API", ""),
        "BACKTEST_INSTANCES": int(os.getenv("BACKTEST_INSTANCES", 1)),
        "MASTER_AUTH_KEY": os.getenv("MASTER_AUTH_KEY", ""),
        # Ajoute ici d'autres variables si nécessaire
    }
''',

        'runner.py': '''from collections import namedtuple
from utils.logging import setup_logger

logger = setup_logger(__name__)

BacktestResult = namedtuple("BacktestResult", ["profit", "sharpe", "equity_curve"])

class BacktestRunner:
    def __init__(self, config: dict):
        self.config = config

    def run(self) -> BacktestResult:
        """
        Exécute un backtest, renvoie profit, Sharpe ratio et equity curve.
        (À compléter avec ta logique métier.)
        """
        logger.info("🔄 Démarrage du backtest")
        # -- Exemple dummy ; remplace par ton simulateur réel --
        profit = 0.05
        sharpe = 1.2
        equity_curve = []
        # Ici : load_backtest_state(), run_backtest(), réinvestissement composé...
        logger.info(f"✅ Backtest terminé (profit={profit}, sharpe={sharpe})")
        return BacktestResult(profit, sharpe, equity_curve)
''',

        'orchestrator.py': '''import threading
from backend.runner import BacktestRunner, BacktestResult
from utils.logging import setup_logger

logger = setup_logger(__name__)

class Orchestrator:
    def __init__(self, config: dict):
        self.config = config
        self.results: list[BacktestResult] = []

    def _run_instance(self, idx: int):
        logger.info(f"�-�️  Lancement instance #{idx}")
        runner = BacktestRunner(self.config)
        result = runner.run()
        self.results.append(result)
        logger.info(f"🏁 Instance #{idx} terminée : {result}")

    def run_backtests(self) -> BacktestResult:
        """
        Lance en parallèle N backtests et retourne le meilleur résultat.
        """
        threads = []
        n = self.config["BACKTEST_INSTANCES"]
        logger.info(f"⚙️  Démarrage de {n} instances de backtest")
        for i in range(n):
            t = threading.Thread(target=self._run_instance, args=(i,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        best = max(self.results, key=lambda r: r.sharpe)
        logger.info(f"⭐ Meilleur backtest sélectionné : {best}")
        return best

    def run_live(self, best: BacktestResult):
        """
        Passe en mode live avec la configuration issue du meilleur backtest.
        (À compléter avec ta logique de trading live.)
        """
        logger.info("🚀 Passage en mode LIVE")
        # Exemple : start_live_trading(best)
        pass
''',

        'main.py': '''from backend.loader import load_config
from backend.orchestrator import Orchestrator
import logging

def main():
    # Chargement config
    config = load_config()
    if not config["MASTER_AUTH_KEY"] or not config["BINANCE_API"]:
        raise RuntimeError("MASTER_AUTH_KEY ou BINANCE_API manquant !")

    # Initialisation du logger racine
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Backtests
    orchestrator = Orchestrator(config)
    best_result = orchestrator.run_backtests()

    # Live
    orchestrator.run_live(best_result)

if __name__ == "__main__":
    main()
'''
    }

    for filename, content in files_content.items():
        path = os.path.join(backend_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Écrit {path}")

if __name__ == '__main__':
    generate_backend()

