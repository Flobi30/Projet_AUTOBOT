#!/usr/bin/env python3
"""
Deploy script to remove ecommerce and arbitrage modules from AUTOBOT production server
"""
import subprocess
import sys
import os
from datetime import datetime

def run_ssh_command(command, description=""):
    """Execute SSH command on production server"""
    ssh_cmd = [
        'ssh', '-i', os.path.expanduser('~/.ssh/id_ed25519_autobot_new'),
        f'root@{os.environ.get("AUTOBOT_SERVER", "SERVER_IP")}', command
    ]
    
    try:
        print(f"🔄 {description}")
        passphrase = os.environ.get("SSH_PASSPHRASE", "")
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, input=f'{passphrase}\n')
        
        if result.returncode == 0:
            print(f"✅ {description} - Success")
            if result.stdout.strip():
                print(f"Output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ {description} - Failed")
            print(f"Error: {result.stderr.strip()}")
            return False
            
    except Exception as e:
        print(f"❌ {description} - Exception: {e}")
        return False

def deploy_cleaned_files():
    """Deploy cleaned backtest files to production server"""
    print("=== AUTOBOT Ecommerce/Arbitrage Module Removal Deployment ===")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    if not run_ssh_command("echo 'SSH connection test'", "Testing SSH connection"):
        print("❌ SSH connection failed. Cannot deploy changes.")
        return False
    
    backup_commands = [
        "cp /home/autobot/Projet_AUTOBOT/src/autobot/ui/backtest_routes.py /home/autobot/Projet_AUTOBOT/src/autobot/ui/backtest_routes.py.backup",
        "cp /home/autobot/Projet_AUTOBOT/src/autobot/ui/templates/backtest.html /home/autobot/Projet_AUTOBOT/src/autobot/ui/templates/backtest.html.backup"
    ]
    
    for cmd in backup_commands:
        run_ssh_command(cmd, f"Backing up files: {cmd.split('/')[-1]}")
    
    print("\n🔄 Copying cleaned files to production server...")
    
    scp_routes = [
        'scp', '-i', '/home/ubuntu/.ssh/id_ed25519_autobot_new',
        '/home/ubuntu/backtest_routes_broken.py',
        'root@144.76.16.177:/home/autobot/Projet_AUTOBOT/src/autobot/ui/backtest_routes.py'
    ]
    
    scp_template = [
        'scp', '-i', '/home/ubuntu/.ssh/id_ed25519_autobot_new', 
        '/home/ubuntu/backtest_template_cleaned.html',
        'root@144.76.16.177:/home/autobot/Projet_AUTOBOT/src/autobot/ui/templates/backtest.html'
    ]
    
    try:
        result_routes = subprocess.run(scp_routes, capture_output=True, text=True, input='2207BMMM\n')
        if result_routes.returncode == 0:
            print("✅ Backtest routes deployed successfully")
        else:
            print(f"❌ Failed to deploy routes: {result_routes.stderr}")
            
        result_template = subprocess.run(scp_template, capture_output=True, text=True, input='2207BMMM\n')
        if result_template.returncode == 0:
            print("✅ Backtest template deployed successfully")
        else:
            print(f"❌ Failed to deploy template: {result_template.stderr}")
            
    except Exception as e:
        print(f"❌ SCP deployment failed: {e}")
        return False
    
    restart_commands = [
        "cd /home/autobot/Projet_AUTOBOT && docker-compose restart autobot",
        "cd /home/autobot/Projet_AUTOBOT && docker-compose restart nginx"
    ]
    
    for cmd in restart_commands:
        run_ssh_command(cmd, f"Restarting services: {cmd.split()[-1]}")
    
    print("\n🔍 Verifying deployment...")
    verification_commands = [
        "curl -s http://localhost:8000/api/backtest/optimization-status | head -20",
        "ls -la /home/autobot/Projet_AUTOBOT/src/autobot/ui/backtest_routes.py",
        "ls -la /home/autobot/Projet_AUTOBOT/src/autobot/ui/templates/backtest.html"
    ]
    
    for cmd in verification_commands:
        run_ssh_command(cmd, f"Verification: {cmd}")
    
    print("\n✅ Ecommerce/Arbitrage module removal deployment completed!")
    print("🎯 AUTOBOT now focuses exclusively on Crypto/FOREX trading")
    
    return True

if __name__ == "__main__":
    success = deploy_cleaned_files()
    sys.exit(0 if success else 1)
