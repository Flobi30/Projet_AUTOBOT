import os
import json
import uuid
import logging
import hashlib
import time
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import jwt
from fastapi import Depends, HTTPException, status, WebSocket
from starlette.websockets import WebSocketDisconnect
import hashlib
import base64

from autobot.autobot_security.config import SECRET_KEY, ALGORITHM
from autobot.autobot_security.auth.jwt_handler import create_access_token, decode_token, verify_license_key, get_current_user

class User(dict):
    """
    Classe User utilisée comme annotation de type pour les dépendances FastAPI.
    Hérite de dict pour maintenir la compatibilité avec le code existant.
    """
    def __init__(self, data: Dict[str, Any]):
        super().__init__(data)
        for key, value in data.items():
            setattr(self, key, value)

logger = logging.getLogger(__name__)

class UserManager:
    """
    User management system for AUTOBOT.
    Handles user authentication, registration, and license management.
    """
    
    def __init__(self, users_file: str = "users.json", encryption_key: str = None):
        """
        Initialize the user manager.
        
        Args:
            users_file: Path to the users database file
            encryption_key: Key for encrypting sensitive data. If None, a key will be derived from SECRET_KEY
        """
        self.users_file = users_file
        self._setup_encryption(encryption_key)
        self.users = self._load_users()
        
    def _setup_encryption(self, encryption_key: str = None):
        """
        Set up simple encryption for sensitive data.
        
        Args:
            encryption_key: Key for encryption. If None, derive from SECRET_KEY
        """
        if encryption_key:
            self.encryption_key = hashlib.sha256(encryption_key.encode()).hexdigest()
        else:
            self.encryption_key = hashlib.sha256(SECRET_KEY.encode()).hexdigest()
        
    def _encrypt_data(self, data: str) -> str:
        """
        Simple encryption for sensitive data.
        
        Args:
            data: Data to encrypt
            
        Returns:
            str: Encrypted data as base64 string
        """
        if not data:
            return data
            
        try:
            encrypted = ''.join(chr(ord(c) ^ ord(self.encryption_key[i % len(self.encryption_key)])) for i, c in enumerate(data))
            return base64.b64encode(encrypted.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption error: {str(e)}")
            return data
            
    def _decrypt_data(self, encrypted_data: str) -> str:
        """
        Simple decryption for sensitive data.
        
        Args:
            encrypted_data: Encrypted data as base64 string
            
        Returns:
            str: Decrypted data
        """
        if not encrypted_data:
            return encrypted_data
            
        try:
            decoded = base64.b64decode(encrypted_data.encode()).decode()
            decrypted = ''.join(chr(ord(c) ^ ord(self.encryption_key[i % len(self.encryption_key)])) for i, c in enumerate(decoded))
            return decrypted
        except Exception as e:
            logger.error(f"Decryption error: {str(e)}")
            return encrypted_data
        
    def _load_users(self) -> Dict[str, Any]:
        """
        Load users from the database file.
        
        Returns:
            Dict: Users data
        """
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading users file: {str(e)}")
                return {"users": {}}
        else:
            return {"users": {}}
    
    def _save_users(self):
        """
        Save users to the database file.
        Ensures sensitive data is encrypted before saving.
        """
        try:
            users_to_save = json.loads(json.dumps(self.users))
            
            # Encrypt sensitive data in the copy
            for username, user in users_to_save["users"].items():
                if "api_keys" in user:
                    for key_data in user["api_keys"]:
                        if not key_data.get("encrypted", False) and "key" in key_data:
                            key_data["key"] = self._encrypt_data(key_data["key"])
                            key_data["encrypted"] = True
            
            # Save the encrypted data
            with open(self.users_file, 'w') as f:
                json.dump(users_to_save, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving users file: {str(e)}")
    
    def register_user(
        self, 
        username: str, 
        password: str, 
        email: str,
        role: str = "user"
    ) -> Dict[str, Any]:
        """
        Register a new user.
        
        Args:
            username: Username
            password: Password
            email: Email address
            role: User role (user, admin)
            
        Returns:
            Dict: User data
        """
        if username in self.users["users"]:
            raise ValueError(f"User {username} already exists")
        
        salt = os.urandom(32).hex()
        password_hash = self._hash_password(password, salt)
        
        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "salt": salt,
            "role": role,
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "licenses": [],
            "api_keys": [],
            "settings": {
                "theme": "dark",
                "notifications_enabled": True
            }
        }
        
        self.users["users"][username] = user
        self._save_users()
        
        return self._clean_user_data(user)
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate a user.
        
        Args:
            username: Username
            password: Password
            
        Returns:
            Dict: User data if authentication successful, None otherwise
        """
        if username not in self.users["users"]:
            return None
        
        user = self.users["users"][username]
        salt = user["salt"]
        password_hash = self._hash_password(password, salt)
        
        if password_hash != user["password_hash"]:
            return None
        
        user["last_login"] = datetime.now().isoformat()
        self._save_users()
        
        return self._clean_user_data(user)
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user by ID.
        
        Args:
            user_id: User ID
            
        Returns:
            Dict: User data if found, None otherwise
        """
        for username, user in self.users["users"].items():
            if user["id"] == user_id:
                return self._clean_user_data(user)
        
        return None
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user by username.
        
        Args:
            username: Username
            
        Returns:
            Dict: User data if found, None otherwise
        """
        if username in self.users["users"]:
            return self._clean_user_data(self.users["users"][username])
        
        return None
    
    def update_user(self, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update user data.
        
        Args:
            user_id: User ID
            data: Data to update
            
        Returns:
            Dict: Updated user data if successful, None otherwise
        """
        for username, user in self.users["users"].items():
            if user["id"] == user_id:
                allowed_fields = ["email", "settings"]
                
                for field in allowed_fields:
                    if field in data:
                        user[field] = data[field]
                
                if "password" in data:
                    salt = os.urandom(32).hex()
                    password_hash = self._hash_password(data["password"], salt)
                    user["password_hash"] = password_hash
                    user["salt"] = salt
                
                self._save_users()
                return self._clean_user_data(user)
        
        return None
    
    def delete_user(self, user_id: str) -> bool:
        """
        Delete a user.
        
        Args:
            user_id: User ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        for username, user in list(self.users["users"].items()):
            if user["id"] == user_id:
                del self.users["users"][username]
                self._save_users()
                return True
        
        return False
    
    def add_license(self, user_id: str, license_key: str, features: List[str], expiration_days: int = 365) -> bool:
        """
        Add a license to a user.
        
        Args:
            user_id: User ID
            license_key: License key
            features: List of features to enable
            expiration_days: Number of days until expiration
            
        Returns:
            bool: True if successful, False otherwise
        """
        for username, user in self.users["users"].items():
            if user["id"] == user_id:
                for license in user["licenses"]:
                    if license["key"] == license_key:
                        return False
                
                license_data = {
                    "key": license_key,
                    "features": features,
                    "created_at": int(time.time()),
                    "expires_at": int(time.time() + expiration_days * 86400),
                    "active": True
                }
                
                user["licenses"].append(license_data)
                self._save_users()
                return True
        
        return False
    
    def verify_license(self, user_id: str, license_key: str) -> bool:
        """
        Verify if a user has a valid license.
        
        Args:
            user_id: User ID
            license_key: License key
            
        Returns:
            bool: True if license is valid, False otherwise
        """
        for username, user in self.users["users"].items():
            if user["id"] == user_id:
                for license in user["licenses"]:
                    if license["key"] == license_key and license["active"]:
                        if license["expires_at"] < int(time.time()):
                            license["active"] = False
                            self._save_users()
                            return False
                        
                        return True
        
        return False
    
    def create_api_key(self, user_id: str, name: str, permissions: List[str]) -> Optional[str]:
        """
        Create an API key for a user.
        
        Args:
            user_id: User ID
            name: Name of the API key
            permissions: List of permissions
            
        Returns:
            str: API key if successful, None otherwise
        """
        for username, user in self.users["users"].items():
            if user["id"] == user_id:
                api_key = f"autobot_{uuid.uuid4().hex}"
                
                encrypted_key = self._encrypt_data(api_key)
                
                api_key_data = {
                    "key": encrypted_key,
                    "name": name,
                    "permissions": permissions,
                    "created_at": int(time.time()),
                    "last_used": None,
                    "encrypted": True
                }
                
                user["api_keys"].append(api_key_data)
                self._save_users()
                return api_key  # Return unencrypted key to user
        
        return None
    
    def verify_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Verify an API key and return the associated user.
        
        Args:
            api_key: API key
            
        Returns:
            Dict: User data if API key is valid, None otherwise
        """
        for username, user in self.users["users"].items():
            for key_data in user["api_keys"]:
                stored_key = key_data["key"]
                
                if key_data.get("encrypted", False):
                    decrypted_key = self._decrypt_data(stored_key)
                    if decrypted_key == api_key:
                        key_data["last_used"] = int(time.time())
                        self._save_users()
                        
                        return {
                            "user": self._clean_user_data(user),
                            "permissions": key_data["permissions"]
                        }
                elif stored_key == api_key:
                    key_data["key"] = self._encrypt_data(api_key)
                    key_data["encrypted"] = True
                    key_data["last_used"] = int(time.time())
                    self._save_users()
                    
                    return {
                        "user": self._clean_user_data(user),
                        "permissions": key_data["permissions"]
                    }
        
        return None
    
    def create_token(self, user_id: str, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create an access token for a user.
        
        Args:
            user_id: User ID
            expires_delta: Token expiration time
            
        Returns:
            str: Access token
        """
        user = self.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        data = {
            "sub": user_id,
            "username": user["username"],
            "role": user["role"]
        }
        
        return create_access_token(data, expires_delta)
    
    def _hash_password(self, password: str, salt: str) -> str:
        """
        Hash a password with a salt.
        
        Args:
            password: Password
            salt: Salt
            
        Returns:
            str: Hashed password
        """
        return hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            bytes.fromhex(salt),
            100000
        ).hex()
    
    def _clean_user_data(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove sensitive information from user data.
        
        Args:
            user: User data
            
        Returns:
            Dict: Cleaned user data
        """
        user_copy = user.copy()
        sensitive_fields = ["password_hash", "salt"]
        
        for field in sensitive_fields:
            if field in user_copy:
                del user_copy[field]
        
        if "api_keys" in user_copy:
            api_keys = []
            for key_data in user_copy["api_keys"]:
                key_data_copy = key_data.copy()
                
                if key_data.get("encrypted", False):
                    try:
                        full_key = self._decrypt_data(key_data_copy["key"])
                        key_data_copy["key"] = full_key[:8] + "..." + full_key[-4:]
                    except Exception as e:
                        logger.error(f"Error decrypting API key for display: {str(e)}")
                        key_data_copy["key"] = "********"
                else:
                    key_data_copy["key"] = key_data_copy["key"][:8] + "..." + key_data_copy["key"][-4:]
                
                api_keys.append(key_data_copy)
            
            user_copy["api_keys"] = api_keys
        
        return user_copy

async def get_current_user_ws(websocket: WebSocket) -> User:
    """
    Authenticate user from WebSocket connection.
    Similar to get_current_user but adapted for WebSocket connections.
    
    Args:
        websocket: WebSocket connection
        
    Returns:
        User: Authenticated user
        
    Raises:
        WebSocketDisconnect: If authentication fails
    """
    try:
        token = websocket.query_params.get("token")
        if not token:
            token = websocket.cookies.get("access_token")
            
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)
            
        payload = decode_token(token)
        user_data = {"id": payload.get("sub"), "username": payload.get("username"), "role": payload.get("role")}
        return User(user_data)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)
