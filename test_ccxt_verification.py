#!/usr/bin/env python3
"""
Test CCXT provider functionality for AUTOBOT system verification
"""
import sys
import os
sys.path.append('/home/ubuntu/Projet_AUTOBOT/src')

try:
    from autobot.providers.ccxt_provider_enhanced import get_exchanges
    print('CCXT provider test: SUCCESS')
    exchanges = get_exchanges()
    print(f'Available exchanges: {exchanges[:5]}')
    print(f'Total exchanges: {len(exchanges)}')
except Exception as e:
    print(f'CCXT provider test: FAILED - {str(e)}')
