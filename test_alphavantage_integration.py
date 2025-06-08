#!/usr/bin/env python3
"""
Test AlphaVantage provider functionality for AUTOBOT system verification
"""
import sys
import os
sys.path.append('/home/ubuntu/Projet_AUTOBOT/src')

try:
    from autobot.providers.alphavantage import get_time_series
    print('AlphaVantage provider test: SUCCESS')
    result = get_time_series('AAPL')
    print(f'AlphaVantage result type: {type(result)}')
    if isinstance(result, dict) and 'error' in result:
        print(f'AlphaVantage error: {result["error"]}')
    else:
        print('AlphaVantage data retrieved successfully')
except Exception as e:
    print(f'AlphaVantage provider test: FAILED - {str(e)}')
