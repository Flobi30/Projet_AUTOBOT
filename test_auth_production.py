import sys
import os
sys.path.append('/home/ubuntu/Projet_AUTOBOT/src')

from autobot.autobot_security.auth.user_manager import UserManager

um = UserManager()
user = um.authenticate_user('AUTOBOT', '333333Aesnpr54&')
print('Auth result:', user is not None)
if user:
    print('User ID:', user.get('id'))
    license_valid = um.verify_license(user['id'], 'AUTOBOT-eyJ0eXAi-OiJKV1Qi-LCJhbGci-OiJIUzUx')
    print('License valid:', license_valid)
else:
    print('Authentication failed')
