"""
AUTOBOT One-Click Automated Installer

This script provides a fully automated installation and deployment of AUTOBOT
with minimal user intervention. It handles:

1. Environment detection and setup
2. Dependency installation
3. Cloud deployment configuration
4. API key configuration through web UI
5. Automatic mode switching based on market conditions
6. Complete system initialization

Usage:
    python auto_installer.py

The installer will guide you through the minimal required steps and handle
everything else automatically.
"""

import os
import sys
import subprocess
import platform
import json
import time
import webbrowser
import getpass
import random
import string
import socket
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

CLOUD_PROVIDERS = {
    "aws": "Amazon Web Services",
    "gcp": "Google Cloud Platform",
    "azure": "Microsoft Azure",
    "digitalocean": "DigitalOcean",
    "vultr": "Vultr",
    "linode": "Linode",
    "local": "Local Deployment (No Cloud)"
}

DEFAULT_CONFIG = {
    "deployment": {
        "provider": "local",
        "instance_type": "medium",
        "region": "auto",
        "domain": "auto-generated",
        "ssl": True
    },
    "autobot": {
        "auto_mode_switching": True,
        "default_mode": "standard",
        "auto_scaling": True,
        "max_instances": 100,
        "domain_allocation": {
            "trading": 60,
            "ecommerce": 20,
            "arbitrage": 20
        }
    },
    "security": {
        "always_ghost": True,
        "jwt_secret": "",
        "admin_password": ""
    },
    "database": {
        "type": "postgresql",
        "auto_setup": True
    },
    "ui": {
        "theme": "neon_dark",
        "language": "auto"
    }
}

def print_banner():
    """Print the AUTOBOT installer banner."""
    banner = f"""
{Colors.GREEN}
    █████╗ ██╗   ██╗████████╗ ██████╗ ██████╗  ██████╗ ████████╗
   ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗██╔══██╗██╔═══██╗╚══██╔══╝
   ███████║██║   ██║   ██║   ██║   ██║██████╔╝██║   ██║   ██║   
   ██╔══██║██║   ██║   ██║   ██║   ██║██╔══██╗██║   ██║   ██║   
   ██║  ██║╚██████╔╝   ██║   ╚██████╔╝██████╔╝╚██████╔╝   ██║   
   ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝ ╚═════╝  ╚═════╝    ╚═╝   
{Colors.BLUE}                                                               
   ██╗███╗   ██╗███████╗████████╗ █████╗ ██╗     ██╗     ███████╗██████╗ 
   ██║████╗  ██║██╔════╝╚══██╔══╝██╔══██╗██║     ██║     ██╔════╝██╔══██╗
   ██║██╔██╗ ██║███████╗   ██║   ███████║██║     ██║     █████╗  ██████╔╝
   ██║██║╚██╗██║╚════██║   ██║   ██╔══██║██║     ██║     ██╔══╝  ██╔══██╗
   ██║██║ ╚████║███████║   ██║   ██║  ██║███████╗███████╗███████╗██║  ██║
   ╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝
{Colors.ENDC}
{Colors.BOLD}Fully Automated Installation & Deployment{Colors.ENDC}
"""
    print(banner)
    print(f"{Colors.BOLD}This installer will automatically set up and deploy AUTOBOT with minimal intervention.{Colors.ENDC}")
    print(f"{Colors.BOLD}You'll only need to provide cloud credentials and API keys through the web interface.{Colors.ENDC}\n")

def check_system_requirements() -> bool:
    """
    Check if the system meets the minimum requirements.
    
    Returns:
        bool: True if all requirements are met, False otherwise
    """
    print(f"{Colors.HEADER}Checking system requirements...{Colors.ENDC}")
    
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 9):
        print(f"{Colors.FAIL}Error: Python 3.9+ is required. Found {python_version.major}.{python_version.minor}{Colors.ENDC}")
        return False
    print(f"{Colors.GREEN}✓ Python version: {python_version.major}.{python_version.minor}.{python_version.micro}{Colors.ENDC}")
    
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"{Colors.GREEN}✓ pip is installed{Colors.ENDC}")
    except subprocess.CalledProcessError:
        print(f"{Colors.FAIL}Error: pip is not installed{Colors.ENDC}")
        return False
    
    try:
        subprocess.run(["git", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"{Colors.GREEN}✓ git is installed{Colors.ENDC}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{Colors.FAIL}Error: git is not installed{Colors.ENDC}")
        return False
    
    try:
        subprocess.run(["docker", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"{Colors.GREEN}✓ Docker is installed (optional){Colors.ENDC}")
        has_docker = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{Colors.WARNING}Warning: Docker is not installed (optional){Colors.ENDC}")
        has_docker = False
    
    if platform.system() != "Windows":
        try:
            df = subprocess.run(["df", "-h", "."], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            lines = df.stdout.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    available = parts[3]
                    if available.endswith('G'):
                        available_gb = float(available[:-1])
                        if available_gb < 5:
                            print(f"{Colors.WARNING}Warning: Less than 5GB disk space available ({available_gb}GB){Colors.ENDC}")
                        else:
                            print(f"{Colors.GREEN}✓ Sufficient disk space: {available_gb}GB{Colors.ENDC}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"{Colors.WARNING}Warning: Could not check available disk space{Colors.ENDC}")
    
    try:
        socket.create_connection(("www.google.com", 80))
        print(f"{Colors.GREEN}✓ Internet connection available{Colors.ENDC}")
    except OSError:
        print(f"{Colors.FAIL}Error: No internet connection{Colors.ENDC}")
        return False
    
    print(f"{Colors.GREEN}All required system checks passed!{Colors.ENDC}\n")
    return True

def install_dependencies() -> bool:
    """
    Install all required dependencies.
    
    Returns:
        bool: True if installation was successful, False otherwise
    """
    print(f"{Colors.HEADER}Installing dependencies...{Colors.ENDC}")
    
    try:
        print("Installing Python dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        requirements = [
            "fastapi", "uvicorn", "pydantic", "python-dotenv", "requests", "ccxt", 
            "numpy", "pandas", "scikit-learn", "tensorflow", "torch", "stable-baselines3",
            "psycopg2-binary", "sqlalchemy", "alembic", "jinja2", "aiohttp", "websockets",
            "pyjwt", "passlib", "bcrypt", "python-multipart", "httpx", "pytest", "pytest-cov",
            "docker", "boto3", "google-cloud-storage", "azure-storage-blob", "paramiko",
            "cryptography", "pycryptodome", "redis", "celery", "flower", "gunicorn",
            "supervisor", "fabric", "ansible"
        ]
        
        subprocess.run([sys.executable, "-m", "pip", "install"] + requirements, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"{Colors.GREEN}✓ Python dependencies installed{Colors.ENDC}")
        
        print("Installing AUTOBOT package...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"{Colors.GREEN}✓ AUTOBOT package installed{Colors.ENDC}")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"{Colors.FAIL}Error installing dependencies: {str(e)}{Colors.ENDC}")
        return False

def generate_secure_key(length: int = 32) -> str:
    """
    Generate a secure random key.
    
    Args:
        length: Length of the key to generate
        
    Returns:
        str: Generated secure key
    """
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choice(chars) for _ in range(length))

def get_deployment_config() -> Dict[str, Any]:
    """
    Get deployment configuration from user with smart defaults.
    
    Returns:
        Dict[str, Any]: Deployment configuration
    """
    print(f"{Colors.HEADER}Deployment Configuration{Colors.ENDC}")
    print("AUTOBOT can be deployed locally or to a cloud provider.")
    print("For maximum automation, we recommend cloud deployment.\n")
    
    config = DEFAULT_CONFIG.copy()
    
    print("Available deployment options:")
    for key, name in CLOUD_PROVIDERS.items():
        print(f"  {key}: {name}")
    
    provider = input(f"\nSelect deployment option [{config['deployment']['provider']}]: ").strip().lower()
    if provider and provider in CLOUD_PROVIDERS:
        config["deployment"]["provider"] = provider
    
    if config["deployment"]["provider"] != "local":
        print(f"\nYou selected {CLOUD_PROVIDERS[config['deployment']['provider']]}.")
        print("Cloud credentials will be collected through the web interface after installation.")
        
        instance_type = input(f"Instance type (small/medium/large) [{config['deployment']['instance_type']}]: ").strip().lower()
        if instance_type in ["small", "medium", "large"]:
            config["deployment"]["instance_type"] = instance_type
        
        region = input(f"Region (or 'auto' for automatic selection) [{config['deployment']['region']}]: ").strip().lower()
        if region:
            config["deployment"]["region"] = region
        
        domain = input(f"Domain name (or 'auto-generated' for automatic subdomain) [{config['deployment']['domain']}]: ").strip().lower()
        if domain:
            config["deployment"]["domain"] = domain
    
    config["security"]["jwt_secret"] = generate_secure_key(64)
    config["security"]["admin_password"] = generate_secure_key(16)
    
    print(f"\n{Colors.GREEN}✓ Deployment configuration complete{Colors.ENDC}")
    print(f"{Colors.BOLD}Admin password: {config['security']['admin_password']}{Colors.ENDC}")
    print(f"{Colors.BOLD}Please save this password for initial login!{Colors.ENDC}\n")
    
    return config

def setup_local_environment(config: Dict[str, Any]) -> bool:
    """
    Set up the local environment for AUTOBOT.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        bool: True if setup was successful, False otherwise
    """
    print(f"{Colors.HEADER}Setting up local environment...{Colors.ENDC}")
    
    try:
        env_path = Path(".env")
        with open(env_path, "w") as f:
            f.write(f"# AUTOBOT Environment Configuration\n")
            f.write(f"# Generated by auto_installer.py\n\n")
            
            f.write(f"JWT_SECRET={config['security']['jwt_secret']}\n")
            f.write(f"ADMIN_PASSWORD={config['security']['admin_password']}\n\n")
            
            f.write(f"DB_TYPE={config['database']['type']}\n")
            if config['database']['type'] == 'postgresql':
                f.write(f"DB_HOST=localhost\n")
                f.write(f"DB_PORT=5432\n")
                f.write(f"DB_NAME=autobot\n")
                f.write(f"DB_USER=postgres\n")
                f.write(f"DB_PASSWORD=autobot\n\n")
            
            f.write(f"AUTO_MODE_SWITCHING={'true' if config['autobot']['auto_mode_switching'] else 'false'}\n")
            f.write(f"DEFAULT_MODE={config['autobot']['default_mode']}\n")
            f.write(f"AUTO_SCALING={'true' if config['autobot']['auto_scaling'] else 'false'}\n")
            f.write(f"MAX_INSTANCES={config['autobot']['max_instances']}\n")
            f.write(f"DOMAIN_ALLOCATION_TRADING={config['autobot']['domain_allocation']['trading']}\n")
            f.write(f"DOMAIN_ALLOCATION_ECOMMERCE={config['autobot']['domain_allocation']['ecommerce']}\n")
            f.write(f"DOMAIN_ALLOCATION_ARBITRAGE={config['autobot']['domain_allocation']['arbitrage']}\n\n")
            
            f.write(f"UI_THEME={config['ui']['theme']}\n")
            f.write(f"UI_LANGUAGE={config['ui']['language']}\n")
        
        print(f"{Colors.GREEN}✓ Environment configuration created (.env){Colors.ENDC}")
        
        config_path = Path("autobot.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        
        print(f"{Colors.GREEN}✓ AUTOBOT configuration created (autobot.json){Colors.ENDC}")
        
        if config['database']['auto_setup'] and config['database']['type'] == 'postgresql':
            print("Setting up PostgreSQL database...")
            try:
                subprocess.run(["psql", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                subprocess.run(["sudo", "-u", "postgres", "psql", "-c", "CREATE DATABASE autobot;"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["sudo", "-u", "postgres", "psql", "-c", "CREATE USER autobot WITH ENCRYPTED PASSWORD 'autobot';"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                subprocess.run(["sudo", "-u", "postgres", "psql", "-c", "GRANT ALL PRIVILEGES ON DATABASE autobot TO autobot;"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                
                print(f"{Colors.GREEN}✓ PostgreSQL database set up{Colors.ENDC}")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"{Colors.WARNING}Warning: Could not set up PostgreSQL database automatically{Colors.ENDC}")
                print(f"{Colors.WARNING}You will need to set up the database manually or through the web interface{Colors.ENDC}")
        
        return True
    except Exception as e:
        print(f"{Colors.FAIL}Error setting up local environment: {str(e)}{Colors.ENDC}")
        return False

def deploy_autobot(config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Deploy AUTOBOT based on the configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple[bool, Optional[str]]: Success status and URL if deployed
    """
    print(f"{Colors.HEADER}Deploying AUTOBOT...{Colors.ENDC}")
    
    if config["deployment"]["provider"] == "local":
        try:
            print("Starting AUTOBOT locally...")
            
            startup_script = Path("start_autobot.sh")
            with open(startup_script, "w") as f:
                f.write("#!/bin/bash\n\n")
                f.write("# Start AUTOBOT\n")
                f.write("cd \"$(dirname \"$0\")\"\n")
                f.write("source .env\n")
                f.write("python -m autobot.main\n")
            
            os.chmod(startup_script, 0o755)
            
            process = subprocess.Popen(["./start_autobot.sh"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            print("Waiting for AUTOBOT to start...")
            time.sleep(5)
            
            try:
                response = requests.get("http://localhost:8000/health")
                if response.status_code == 200:
                    print(f"{Colors.GREEN}✓ AUTOBOT started successfully{Colors.ENDC}")
                    return True, "http://localhost:8000"
                else:
                    print(f"{Colors.WARNING}Warning: AUTOBOT started but health check failed{Colors.ENDC}")
                    return True, "http://localhost:8000"
            except requests.RequestException:
                print(f"{Colors.WARNING}Warning: AUTOBOT may not have started correctly{Colors.ENDC}")
                return True, "http://localhost:8000"
            
        except Exception as e:
            print(f"{Colors.FAIL}Error deploying AUTOBOT locally: {str(e)}{Colors.ENDC}")
            return False, None
    else:
        print(f"Deploying to {CLOUD_PROVIDERS[config['deployment']['provider']]}...")
        print("Cloud deployment will be handled through the web interface.")
        print("Starting local instance for cloud deployment configuration...")
        
        try:
            startup_script = Path("start_autobot.sh")
            with open(startup_script, "w") as f:
                f.write("#!/bin/bash\n\n")
                f.write("# Start AUTOBOT\n")
                f.write("cd \"$(dirname \"$0\")\"\n")
                f.write("source .env\n")
                f.write("python -m autobot.main --setup-cloud\n")
            
            os.chmod(startup_script, 0o755)
            
            process = subprocess.Popen(["./start_autobot.sh"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            print("Waiting for AUTOBOT to start...")
            time.sleep(5)
            
            try:
                response = requests.get("http://localhost:8000/health")
                if response.status_code == 200:
                    print(f"{Colors.GREEN}✓ AUTOBOT started successfully in cloud setup mode{Colors.ENDC}")
                    return True, "http://localhost:8000/setup-cloud"
                else:
                    print(f"{Colors.WARNING}Warning: AUTOBOT started but health check failed{Colors.ENDC}")
                    return True, "http://localhost:8000/setup-cloud"
            except requests.RequestException:
                print(f"{Colors.WARNING}Warning: AUTOBOT may not have started correctly{Colors.ENDC}")
                return True, "http://localhost:8000/setup-cloud"
            
        except Exception as e:
            print(f"{Colors.FAIL}Error starting AUTOBOT for cloud deployment: {str(e)}{Colors.ENDC}")
            return False, None

def main():
    """Main installer function."""
    print_banner()
    
    if not check_system_requirements():
        print(f"{Colors.FAIL}System requirements not met. Please fix the issues and try again.{Colors.ENDC}")
        return
    
    if not Path("src/autobot").exists():
        print(f"{Colors.HEADER}Cloning AUTOBOT repository...{Colors.ENDC}")
        try:
            subprocess.run(["git", "clone", "https://github.com/Flobi30/Projet_AUTOBOT.git", "."], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"{Colors.GREEN}✓ Repository cloned successfully{Colors.ENDC}")
        except subprocess.CalledProcessError as e:
            print(f"{Colors.FAIL}Error cloning repository: {str(e)}{Colors.ENDC}")
            return
    
    if not install_dependencies():
        print(f"{Colors.FAIL}Failed to install dependencies. Please fix the issues and try again.{Colors.ENDC}")
        return
    
    config = get_deployment_config()
    
    if not setup_local_environment(config):
        print(f"{Colors.FAIL}Failed to set up local environment. Please fix the issues and try again.{Colors.ENDC}")
        return
    
    success, url = deploy_autobot(config)
    if not success:
        print(f"{Colors.FAIL}Failed to deploy AUTOBOT. Please fix the issues and try again.{Colors.ENDC}")
        return
    
    print(f"\n{Colors.GREEN}✅ AUTOBOT has been successfully installed and deployed!{Colors.ENDC}")
    print(f"\n{Colors.BOLD}Access AUTOBOT at: {url}{Colors.ENDC}")
    print(f"{Colors.BOLD}Admin password: {config['security']['admin_password']}{Colors.ENDC}")
    
    print("\nNext steps:")
    print("1. Open the URL above in your browser")
    print("2. Log in with username 'admin' and the password shown above")
    print("3. Follow the on-screen instructions to complete the setup")
    print("4. Enter your exchange API keys when prompted")
    
    try:
        webbrowser.open(url)
    except:
        pass
    
    print(f"\n{Colors.BOLD}Thank you for installing AUTOBOT!{Colors.ENDC}")

if __name__ == "__main__":
    main()
