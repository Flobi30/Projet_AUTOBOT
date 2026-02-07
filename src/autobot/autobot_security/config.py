# Configuration for AUTOBOT Security Module
import os

_DEFAULT_INSECURE_KEY = 'your-secret-key-change-in-production'

_raw = os.getenv('SECRET_KEY', '')

if not _raw or _raw == _DEFAULT_INSECURE_KEY:
    _env = os.getenv('ENV', 'production').lower()
    if _env not in ('dev', 'development', 'test', 'testing', 'ci'):
        raise RuntimeError(
            "SECURITY ERROR: SECRET_KEY environment variable is not set or uses the insecure default. "
            "Set a strong SECRET_KEY (>= 32 chars) before running in production."
        )
    _raw = _DEFAULT_INSECURE_KEY

SECRET_KEY: str = _raw
ALGORITHM = 'HS256'

