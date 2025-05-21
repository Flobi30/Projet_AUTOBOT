# Configuration for AUTOBOT Security Module
import os
import logging
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "1440"))

if SECRET_KEY == "your-secret-key":
    logging.warning("Using default SECRET_KEY value. This is insecure for production!")

if ALGORITHM != "HS256":
    logging.info(f"Using non-default JWT algorithm: {ALGORITHM}")

