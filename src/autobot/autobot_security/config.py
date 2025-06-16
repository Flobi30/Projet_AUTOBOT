# Configuration for AUTOBOT Security Module
import os

# Define security configuration settings here
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
ALGORITHM = 'HS256'

