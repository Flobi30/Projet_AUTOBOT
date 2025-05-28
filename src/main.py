#!/usr/bin/env python3

import os
import sys

# On ajoute la racine (/app) au PYTHONPATH
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from autobot import AutobotKernel

def main():
    bot = AutobotKernel()
    bot.run()

if __name__ == "__main__":
    main()

