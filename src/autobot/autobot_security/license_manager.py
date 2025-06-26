"""
License Manager for AUTOBOT

This module provides advanced license management capabilities for controlling
instance duplication, feature access, and remote management of AUTOBOT deployments.
"""

import os
import json
import time
import uuid
import hashlib
import hmac
import base64
import logging
import threading
import requests
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
import jwt

logger = logging.getLogger(__name__)

@dataclass
class LicenseFeature:
    """Represents a feature controlled by licensing"""
    name: str
    enabled: bool
    max_usage: Optional[int] = None
    current_usage: int = 0
    expiration: Optional[int] = None  # Unix timestamp


@dataclass
class LicenseInfo:
    """Represents license information"""
    license_id: str
    user_id: str
    created_at: int
    expires_at: Optional[int]
    max_instances: int
    features: Dict[str, LicenseFeature]
    signature: str
    parent_license_id: Optional[str] = None
    instance_id: Optional[str] = None
    last_check: Optional[int] = None
    is_valid: bool = False


class LicenseManager:
    """
    Advanced license manager for controlling AUTOBOT instances.
    Provides capabilities for instance duplication control, feature access,
    and remote management of deployments.
    """
    
    def __init__(
        self,
        license_key: Optional[str] = None,
        license_server: str = "https://api.autobot.ai/license",
        data_dir: str = "data/license",
        instance_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        offline_mode: bool = False,
        check_interval: int = 3600
    ):
        """
        Initialize the license manager.
        
        Args:
            license_key: License key
            license_server: License server URL
            data_dir: Directory for storing license data
            instance_id: Unique instance ID, or None to generate
            secret_key: Secret key for license verification
            offline_mode: Whether to operate in offline mode
            check_interval: Interval in seconds between license checks
        """
        self.license_key = license_key
        self.license_server = license_server
        self.data_dir = data_dir
        self.instance_id = instance_id or self._generate_instance_id()
        self.secret_key = secret_key or os.environ.get("AUTOBOT_LICENSE_SECRET", "default-secret-key")
        self.offline_mode = offline_mode
        self.check_interval = check_interval
        
        self.license_info = None
        self.child_licenses = {}
        self.feature_usage = {}
        
        os.makedirs(data_dir, exist_ok=True)
        
        self.running = True
        self.check_thread = threading.Thread(target=self._license_check_loop)
        self.check_thread.daemon = True
        
        self._load_license_data()
        
        if self.license_info:
            self.check_thread.start()
            logger.info(f"License Manager initialized with license ID: {self.license_info.license_id}")
        else:
            logger.warning("License Manager initialized without a valid license")
    
    def _generate_instance_id(self) -> str:
        """
        Generate a unique instance ID.
        
        Returns:
            str: Unique instance ID
        """
        try:
            import platform
            import socket
            
            hostname = socket.gethostname()
            machine_id = platform.node()
            
            unique_id = f"{hostname}-{machine_id}-{uuid.uuid4()}"
            return hashlib.sha256(unique_id.encode()).hexdigest()
            
        except Exception as e:
            logger.warning(f"Error generating hardware-based instance ID: {str(e)}")
            
            return str(uuid.uuid4())
    
    def _load_license_data(self) -> None:
        """Load license data from file or initialize with provided key"""
        license_file = os.path.join(self.data_dir, "license.json")
        
        if os.path.exists(license_file):
            try:
                with open(license_file, 'r') as f:
                    license_data = json.load(f)
                
                features = {}
                for name, feature_data in license_data.get("features", {}).items():
                    features[name] = LicenseFeature(
                        name=name,
                        enabled=feature_data.get("enabled", False),
                        max_usage=feature_data.get("max_usage"),
                        current_usage=feature_data.get("current_usage", 0),
                        expiration=feature_data.get("expiration")
                    )
                
                self.license_info = LicenseInfo(
                    license_id=license_data.get("license_id", ""),
                    user_id=license_data.get("user_id", ""),
                    created_at=license_data.get("created_at", 0),
                    expires_at=license_data.get("expires_at"),
                    max_instances=license_data.get("max_instances", 1),
                    features=features,
                    signature=license_data.get("signature", ""),
                    parent_license_id=license_data.get("parent_license_id"),
                    instance_id=license_data.get("instance_id", self.instance_id),
                    last_check=license_data.get("last_check"),
                    is_valid=license_data.get("is_valid", False)
                )
                
                if "child_licenses" in license_data:
                    self.child_licenses = license_data["child_licenses"]
                
                logger.info(f"Loaded license data from {license_file}")
                
                self.license_info.is_valid = self._verify_license(self.license_info)
                
            except Exception as e:
                logger.error(f"Error loading license data from {license_file}: {str(e)}")
                self.license_info = None
        
        if not self.license_info and self.license_key:
            self.activate_license(self.license_key)
    
    def _save_license_data(self) -> None:
        """Save license data to file"""
        if not self.license_info:
            return
        
        license_file = os.path.join(self.data_dir, "license.json")
        
        try:
            license_data = {
                "license_id": self.license_info.license_id,
                "user_id": self.license_info.user_id,
                "created_at": self.license_info.created_at,
                "expires_at": self.license_info.expires_at,
                "max_instances": self.license_info.max_instances,
                "features": {
                    name: {
                        "enabled": feature.enabled,
                        "max_usage": feature.max_usage,
                        "current_usage": feature.current_usage,
                        "expiration": feature.expiration
                    }
                    for name, feature in self.license_info.features.items()
                },
                "signature": self.license_info.signature,
                "parent_license_id": self.license_info.parent_license_id,
                "instance_id": self.license_info.instance_id,
                "last_check": self.license_info.last_check,
                "is_valid": self.license_info.is_valid,
                "child_licenses": self.child_licenses
            }
            
            with open(license_file, 'w') as f:
                json.dump(license_data, f, indent=2)
            
            logger.debug(f"Saved license data to {license_file}")
            
        except Exception as e:
            logger.error(f"Error saving license data to {license_file}: {str(e)}")
    
    def activate_license(self, license_key: str) -> bool:
        """
        Activate a license with the provided key.
        
        Args:
            license_key: License key to activate
            
        Returns:
            bool: True if activation was successful
        """
        if self.offline_mode:
            return self._offline_activate(license_key)
        
        try:
            response = requests.post(
                f"{self.license_server}/activate",
                json={
                    "license_key": license_key,
                    "instance_id": self.instance_id
                },
                timeout=10
            )
            
            if response.status_code == 200:
                license_data = response.json()
                
                if "error" in license_data:
                    logger.error(f"License activation error: {license_data['error']}")
                    return False
                
                features = {}
                for name, feature_data in license_data.get("features", {}).items():
                    features[name] = LicenseFeature(
                        name=name,
                        enabled=feature_data.get("enabled", False),
                        max_usage=feature_data.get("max_usage"),
                        current_usage=0,
                        expiration=feature_data.get("expiration")
                    )
                
                self.license_info = LicenseInfo(
                    license_id=license_data.get("license_id", ""),
                    user_id=license_data.get("user_id", ""),
                    created_at=license_data.get("created_at", int(time.time())),
                    expires_at=license_data.get("expires_at"),
                    max_instances=license_data.get("max_instances", 1),
                    features=features,
                    signature=license_data.get("signature", ""),
                    parent_license_id=license_data.get("parent_license_id"),
                    instance_id=self.instance_id,
                    last_check=int(time.time()),
                    is_valid=True
                )
                
                self._save_license_data()
                
                if not self.check_thread.is_alive():
                    self.check_thread.start()
                
                logger.info(f"License activated successfully: {self.license_info.license_id}")
                return True
            else:
                logger.error(f"License activation failed: {response.status_code} - {response.text}")
                return False
            
        except Exception as e:
            logger.error(f"Error activating license: {str(e)}")
            
            return self._offline_activate(license_key)
    
    def _offline_activate(self, license_key: str) -> bool:
        """
        Activate a license offline.
        
        Args:
            license_key: License key to activate
            
        Returns:
            bool: True if activation was successful
        """
        try:
            decoded = jwt.decode(
                license_key,
                self.secret_key,
                algorithms=["HS256"],
                options={"verify_signature": False}
            )
            
            header, payload, signature = license_key.split(".")
            message = f"{header}.{payload}"
            
            expected_signature = hmac.new(
                self.secret_key.encode(),
                message.encode(),
                hashlib.sha256
            ).digest()
            
            expected_signature_b64 = base64.urlsafe_b64encode(expected_signature).decode().rstrip("=")
            
            if signature != expected_signature_b64:
                logger.error("License signature verification failed")
                return False
            
            if "exp" in decoded and decoded["exp"] < time.time():
                logger.error("License has expired")
                return False
            
            features = {}
            for name, feature_data in decoded.get("features", {}).items():
                features[name] = LicenseFeature(
                    name=name,
                    enabled=feature_data.get("enabled", False),
                    max_usage=feature_data.get("max_usage"),
                    current_usage=0,
                    expiration=feature_data.get("expiration")
                )
            
            self.license_info = LicenseInfo(
                license_id=decoded.get("license_id", str(uuid.uuid4())),
                user_id=decoded.get("user_id", ""),
                created_at=decoded.get("iat", int(time.time())),
                expires_at=decoded.get("exp"),
                max_instances=decoded.get("max_instances", 1),
                features=features,
                signature=signature,
                parent_license_id=decoded.get("parent_license_id"),
                instance_id=self.instance_id,
                last_check=int(time.time()),
                is_valid=True
            )
            
            self._save_license_data()
            
            if not self.check_thread.is_alive():
                self.check_thread.start()
            
            logger.info(f"License activated offline: {self.license_info.license_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error activating license offline: {str(e)}")
            return False
    
    def _license_check_loop(self) -> None:
        """Background thread for periodically checking license status"""
        while self.running:
            try:
                self._check_license()
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in license check loop: {str(e)}")
                time.sleep(60)  # Shorter interval on error
    
    def _check_license(self) -> None:
        """Check license status with the license server"""
        if not self.license_info or self.offline_mode:
            return
        
        try:
            response = requests.post(
                f"{self.license_server}/check",
                json={
                    "license_id": self.license_info.license_id,
                    "instance_id": self.instance_id,
                    "feature_usage": self.feature_usage,
                    "child_licenses": list(self.child_licenses.keys())
                },
                timeout=10
            )
            
            if response.status_code == 200:
                license_data = response.json()
                
                if "error" in license_data:
                    logger.error(f"License check error: {license_data['error']}")
                    return
                
                self.license_info.is_valid = license_data.get("is_valid", False)
                self.license_info.last_check = int(time.time())
                
                for name, feature_data in license_data.get("features", {}).items():
                    if name in self.license_info.features:
                        self.license_info.features[name].enabled = feature_data.get("enabled", False)
                        self.license_info.features[name].max_usage = feature_data.get("max_usage")
                        self.license_info.features[name].expiration = feature_data.get("expiration")
                
                for license_id, status in license_data.get("child_licenses", {}).items():
                    if license_id in self.child_licenses:
                        self.child_licenses[license_id]["is_valid"] = status.get("is_valid", False)
                        self.child_licenses[license_id]["last_check"] = int(time.time())
                
                self._save_license_data()
                
                logger.debug(f"License check successful: {self.license_info.license_id}")
                
            else:
                logger.error(f"License check failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error checking license: {str(e)}")
            
            self.license_info.is_valid = self._verify_license(self.license_info)
            self.license_info.last_check = int(time.time())
            self._save_license_data()
    
    def _verify_license(self, license_info: LicenseInfo) -> bool:
        """
        Verify a license offline.
        
        Args:
            license_info: License information to verify
            
        Returns:
            bool: True if license is valid
        """
        if license_info.expires_at and license_info.expires_at < time.time():
            logger.error(f"License {license_info.license_id} has expired")
            return False
        
        if license_info.signature:
            try:
                message = f"{license_info.license_id}.{license_info.user_id}.{license_info.created_at}"
                
                expected_signature = hmac.new(
                    self.secret_key.encode(),
                    message.encode(),
                    hashlib.sha256
                ).digest()
                
                expected_signature_b64 = base64.urlsafe_b64encode(expected_signature).decode().rstrip("=")
                
                if license_info.signature != expected_signature_b64:
                    logger.error(f"License {license_info.license_id} signature verification failed")
                    return False
                
            except Exception as e:
                logger.error(f"Error verifying license signature: {str(e)}")
                return False
        
        return True
    
    def create_child_license(
        self,
        user_id: str,
        max_instances: int,
        features: Dict[str, Dict[str, Any]],
        expires_at: Optional[int] = None,
        custom_id: Optional[str] = None,
        user_specific_limits: Optional[Dict[str, int]] = None
    ) -> Optional[str]:
        """
        Create a child license for distribution.
        
        Args:
            user_id: ID of the user to create license for
            max_instances: Maximum number of instances allowed
            features: Dictionary of features to enable
            expires_at: Expiration timestamp, or None for same as parent
            custom_id: Custom license ID, or None to generate
            user_specific_limits: Dictionary mapping user IDs to their max instance limits
            
        Returns:
            str: Generated license key, or None if creation failed
        """
        if not self.license_info or not self.license_info.is_valid:
            logger.error("Cannot create child license: No valid parent license")
            return None
        
        if "create_licenses" not in self.license_info.features or not self.license_info.features["create_licenses"].enabled:
            logger.error("Parent license does not allow creating child licenses")
            return None
        
        if max_instances > self.license_info.max_instances:
            logger.error(f"Requested max_instances ({max_instances}) exceeds parent limit ({self.license_info.max_instances})")
            return None
        
        license_id = custom_id or str(uuid.uuid4())
        
        if not expires_at and self.license_info.expires_at:
            expires_at = self.license_info.expires_at
        
        license_features = {}
        for name, feature_data in features.items():
            if name in self.license_info.features and self.license_info.features[name].enabled:
                parent_max = self.license_info.features[name].max_usage
                requested_max = feature_data.get("max_usage")
                
                if parent_max is not None and requested_max is not None and requested_max > parent_max:
                    logger.error(f"Requested max_usage for feature {name} ({requested_max}) exceeds parent limit ({parent_max})")
                    return None
                
                license_features[name] = {
                    "enabled": feature_data.get("enabled", True),
                    "max_usage": feature_data.get("max_usage"),
                    "expiration": feature_data.get("expiration")
                }
            else:
                logger.warning(f"Parent license does not have feature {name} enabled, skipping")
        
        payload = {
            "license_id": license_id,
            "user_id": user_id,
            "iat": int(time.time()),
            "exp": expires_at,
            "max_instances": max_instances,
            "features": license_features,
            "parent_license_id": self.license_info.license_id,
            "user_specific_limits": user_specific_limits or {}
        }
        
        license_key = jwt.encode(payload, self.secret_key, algorithm="HS256")
        
        self.child_licenses[license_id] = {
            "user_id": user_id,
            "created_at": int(time.time()),
            "expires_at": expires_at,
            "max_instances": max_instances,
            "features": license_features,
            "is_valid": True,
            "last_check": int(time.time()),
            "user_specific_limits": user_specific_limits or {}
        }
        
        self._save_license_data()
        
        logger.info(f"Created child license {license_id} for user {user_id} with user-specific limits: {user_specific_limits}")
        return license_key
    
    def revoke_child_license(self, license_id: str) -> bool:
        """
        Revoke a child license.
        
        Args:
            license_id: ID of the license to revoke
            
        Returns:
            bool: True if revocation was successful
        """
        if license_id not in self.child_licenses:
            logger.error(f"Child license {license_id} not found")
            return False
        
        if self.offline_mode:
            self.child_licenses[license_id]["is_valid"] = False
            self._save_license_data()
            logger.info(f"Revoked child license {license_id} (offline mode)")
            return True
        
        try:
            response = requests.post(
                f"{self.license_server}/revoke",
                json={
                    "parent_license_id": self.license_info.license_id,
                    "license_id": license_id,
                    "instance_id": self.instance_id
                },
                timeout=10
            )
            
            if response.status_code == 200:
                self.child_licenses.pop(license_id, None)
                self._save_license_data()
                
                logger.info(f"Revoked child license {license_id}")
                return True
            else:
                logger.error(f"License revocation failed: {response.status_code} - {response.text}")
                return False
            
        except Exception as e:
            logger.error(f"Error revoking license: {str(e)}")
            
            self.child_licenses[license_id]["is_valid"] = False
            self._save_license_data()
            
            logger.info(f"Revoked child license {license_id} (offline fallback)")
            return True
    
    def is_license_valid(self) -> bool:
        """
        Check if the current license is valid.
        
        Returns:
            bool: True if license is valid
        """
        if not self.license_info:
            return False
        
        if self.license_info.expires_at and self.license_info.expires_at < time.time():
            return False
        
        return self.license_info.is_valid
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """
        Check if a feature is enabled.
        
        Args:
            feature_name: Name of the feature
            
        Returns:
            bool: True if feature is enabled
        """
        if not self.license_info or not self.license_info.is_valid:
            return False
        
        if feature_name not in self.license_info.features:
            return False
        
        feature = self.license_info.features[feature_name]
        
        if not feature.enabled:
            return False
        
        if feature.expiration and feature.expiration < time.time():
            return False
        
        if feature.max_usage is not None and feature.current_usage >= feature.max_usage:
            return False
        
        return True
    
    def use_feature(self, feature_name: str, usage: int = 1) -> bool:
        """
        Record usage of a feature.
        
        Args:
            feature_name: Name of the feature
            usage: Amount of usage to record
            
        Returns:
            bool: True if usage was recorded successfully
        """
        if not self.is_feature_enabled(feature_name):
            return False
        
        feature = self.license_info.features[feature_name]
        
        if feature.max_usage is not None and feature.current_usage + usage > feature.max_usage:
            return False
        
        feature.current_usage += usage
        
        if feature_name not in self.feature_usage:
            self.feature_usage[feature_name] = 0
        
        self.feature_usage[feature_name] += usage
        
        self._save_license_data()
        
        return True
    
    def get_license_info(self) -> Dict[str, Any]:
        """
        Get information about the current license.
        
        Returns:
            Dict: License information
        """
        if not self.license_info:
            return {
                "is_valid": False,
                "error": "No license activated"
            }
        
        return {
            "license_id": self.license_info.license_id,
            "user_id": self.license_info.user_id,
            "created_at": self.license_info.created_at,
            "expires_at": self.license_info.expires_at,
            "max_instances": self.license_info.max_instances,
            "features": {
                name: {
                    "enabled": feature.enabled,
                    "max_usage": feature.max_usage,
                    "current_usage": feature.current_usage,
                    "expiration": feature.expiration
                }
                for name, feature in self.license_info.features.items()
            },
            "instance_id": self.instance_id,
            "last_check": self.license_info.last_check,
            "is_valid": self.license_info.is_valid,
            "child_licenses_count": len(self.child_licenses)
        }
    
    def get_child_licenses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about child licenses.
        
        Returns:
            Dict: Child license information
        """
        return self.child_licenses
    
    def shutdown(self) -> None:
        """Shutdown the license manager"""
        self.running = False
        
        if self.check_thread.is_alive():
            self.check_thread.join(timeout=1)
        
        logger.info("License Manager shut down")


def create_license_manager(
    license_key: Optional[str] = None,
    license_server: str = "https://api.autobot.ai/license",
    offline_mode: bool = False
) -> LicenseManager:
    """
    Create a new license manager.
    
    Args:
        license_key: License key
        license_server: License server URL
        offline_mode: Whether to operate in offline mode
        
    Returns:
        LicenseManager: New license manager instance
    """
    return LicenseManager(
        license_key=license_key,
        license_server=license_server,
        offline_mode=offline_mode
    )

_license_manager_instance = None

def get_license_manager() -> Optional[LicenseManager]:
    """
    Retourne l'instance singleton du LicenseManager.
    Crée une nouvelle instance si nécessaire.
    
    Returns:
        LicenseManager: Instance du gestionnaire de licences, ou None si la création échoue
    """
    global _license_manager_instance
    
    if _license_manager_instance is None:
        _license_manager_instance = create_license_manager()
        
    return _license_manager_instance
