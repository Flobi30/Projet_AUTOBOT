#!/usr/bin/env python3
"""
Test Shopify provider functionality for AUTOBOT system verification
"""
import sys
import os
sys.path.append('/home/ubuntu/Projet_AUTOBOT/src')

try:
    from autobot.providers.shopify import get_orders
    print('Shopify provider test: SUCCESS')
    result = get_orders()
    print(f'Shopify result type: {type(result)}')
    if isinstance(result, dict) and 'error' in result:
        print(f'Shopify error: {result["error"]}')
    else:
        print('Shopify data retrieved successfully')
except Exception as e:
    print(f'Shopify provider test: FAILED - {str(e)}')
