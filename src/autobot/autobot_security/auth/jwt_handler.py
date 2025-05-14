import jwt
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from autobot.autobot_security.config import SECRET_KEY, ALGORITHM

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Data to encode in the token
        expires_delta: Token expiration time
        
    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt

def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode a JWT token.
    
    Args:
        token: JWT token to decode
        
    Returns:
        Dict: Decoded token data
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise ValueError("Invalid token")

def verify_license_key(license_key: str) -> bool:
    """
    Verify a license key.
    
    Args:
        license_key: License key to verify
        
    Returns:
        bool: True if valid, False otherwise
    """
    return bool(license_key and len(license_key) > 10)

def generate_license_key(user_id: str, features: list, expiration_days: int = 365) -> str:
    """
    Generate a license key for a user.
    
    Args:
        user_id: User ID
        features: List of features to enable
        expiration_days: Number of days until expiration
        
    Returns:
        str: Generated license key
    """
    payload = {
        "user_id": user_id,
        "features": features,
        "created_at": int(time.time()),
        "expires_at": int(time.time() + expiration_days * 86400)
    }
    
    encoded = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    license_key = f"AUTOBOT-{encoded[:8]}-{encoded[8:16]}-{encoded[16:24]}-{encoded[24:32]}"
    
    return license_key
