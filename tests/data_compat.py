"""
Module de compatibilité pour les tests.
Permet d'importer les providers depuis le package data.
"""
from src.data.providers import AlphaVantageProvider, TwelveDataProvider, CCXTProvider

class Providers:
    AlphaVantageProvider = AlphaVantageProvider
    TwelveDataProvider = TwelveDataProvider
    CCXTProvider = CCXTProvider

data = type('data', (), {'providers': Providers})

import sys
sys.modules['data.providers'] = Providers
