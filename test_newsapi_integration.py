#!/usr/bin/env python3
"""
Test NewsAPI provider functionality for AUTOBOT system verification
"""
import sys
import os
sys.path.append('/home/ubuntu/Projet_AUTOBOT/src')

try:
    from autobot.providers.newsapi import get_news
    print('NewsAPI provider test: SUCCESS')
    result = get_news('bitcoin')
    print(f'NewsAPI result type: {type(result)}')
    if isinstance(result, dict) and 'error' in result:
        print(f'NewsAPI error: {result["error"]}')
    else:
        print('NewsAPI data retrieved successfully')
except Exception as e:
    print(f'NewsAPI provider test: FAILED - {str(e)}')
