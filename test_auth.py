#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '/home/ubuntu/Projet_AUTOBOT/src')

from autobot.autobot_security.auth.user_manager import UserManager

def test_authentication():
    print("Testing AUTOBOT authentication...")
    
    um = UserManager()
    print(f"Users file: {um.users_file}")
    print(f"Users loaded: {list(um.users['users'].keys())}")
    
    test_username = os.getenv('TEST_USERNAME', 'AUTOBOT')
    test_password = os.getenv('TEST_PASSWORD', 'test_password')
    
    result = um.authenticate_user(test_username, test_password)
    print(f'Auth result: {result}')
    
    if result:
        print('User authenticated successfully')
    else:
        print('Authentication failed')
        user = um.users['users'][test_username]
        salt = user['salt']
        password_hash = um._hash_password(test_password, salt)
        print(f'Expected hash: {user["password_hash"]}')
        print(f'Computed hash: {password_hash}')
        print(f'Hashes match: {password_hash == user["password_hash"]}')
        
        print("\nTrying to update password hash...")
        new_salt = "0000000000000000000000000000000000000000000000000000000000000000"
        new_hash = um._hash_password(test_password, new_salt)
        print(f'New hash with same salt: {new_hash}')

if __name__ == "__main__":
    test_authentication()
