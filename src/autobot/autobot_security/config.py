# Configuration for AUTOBOT Security Module
import os
import json
import logging

AUTH_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config', 'auth_config.json')

SECRET_KEY = 'your-secret-key'
ALGORITHM = 'HS256'

try:
    if os.path.exists(AUTH_CONFIG_PATH):
        with open(AUTH_CONFIG_PATH, 'r') as f:
            auth_config = json.load(f)
            SECRET_KEY = auth_config.get('jwt_secret', SECRET_KEY)
            ALGORITHM = auth_config.get('jwt_algorithm', ALGORITHM)
except Exception as e:
    logging.error(f"Error loading auth_config.json: {str(e)}")
    logging.warning("Using default SECRET_KEY and ALGORITHM values")

