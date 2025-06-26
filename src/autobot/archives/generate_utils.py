#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os


def generate_utils():
    u = 'utils'
    os.makedirs(u, exist_ok=True)

    # logging.py
    logpy = '''import logging

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler.setFormatter(fmt)
    if not logger.handlers:
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
'''
    with open(f'{u}/logging.py','w',encoding='utf-8') as f:
        f.write(logpy)

    # secret_vault.py
    vaultpy = '''from cryptography.fernet import Fernet

class SecretVault:
    def __init__(self, master_key: str):
        self.fernet = Fernet(master_key)
    def encrypt(self, data: str) -> bytes:
        return self.fernet.encrypt(data.encode())
    def decrypt(self, token: bytes) -> str:
        return self.fernet.decrypt(token).decode()
'''
    with open(f'{u}/secret_vault.py','w',encoding='utf-8') as f:
        f.write(vaultpy)

    # data_loader.py
    loaderpy = '''import requests, time
from typing import Any, Dict

def fetch_data(primary_url: str, secondary_url: str, params: Dict=None) -> Any:
    retries, backoff = 3, 1
    for _ in range(retries):
        try:
            r = requests.get(primary_url, params=params, timeout=5)
            r.raise_for_status()
            return r.json()
        except:
            time.sleep(backoff)
            backoff *= 2
    r = requests.get(secondary_url, params=params, timeout=5)
    r.raise_for_status()
    return r.json()
'''
    with open(f'{u}/data_loader.py','w',encoding='utf-8') as f:
        f.write(loaderpy)

if __name__ == '__main__':
    generate_utils()

