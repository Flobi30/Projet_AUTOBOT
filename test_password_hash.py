import hashlib
import os
import sys
sys.path.append('/home/ubuntu/Projet_AUTOBOT/src')

from autobot.autobot_security.auth.user_manager import UserManager

password = '333333Aesnpr54&'
salt = '0000000000000000000000000000000000000000000000000000000000000000'

expected_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000)
print('Expected hash:', expected_hash.hex())
print('Current hash in users.json: 8a4af613cf79e366d4829383396ca90175dd82cdb3e30ea7f148348597ea16e5')
print('Match:', expected_hash.hex() == '8a4af613cf79e366d4829383396ca90175dd82cdb3e30ea7f148348597ea16e5')

user_manager = UserManager()
print('\nTesting UserManager authentication:')
user = user_manager.authenticate_user('AUTOBOT', password)
print('Authentication result:', user)

if user:
    print('User ID:', user.get('id'))
    license_valid = user_manager.verify_license(user['id'], 'AUTOBOT-eyJ0eXAi-OiJKV1Qi-LCJhbGci-OiJIUzUx')
    print('License verification:', license_valid)
