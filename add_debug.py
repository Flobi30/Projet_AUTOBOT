with open('/opt/Projet_AUTOBOT/src/autobot/v2/api/dashboard.py', 'r') as f:
    content = f.read()

# Add debug logging to verify_token
old_code = '''    if credentials.credentials.strip() != expected_token.strip():
        raise HTTPException(status_code=403, detail="Token invalide")'''

new_code = '''    if credentials.credentials.strip() != expected_token.strip():
        logger.warning(f"Token mismatch. Received: {repr(credentials.credentials[:20])}... Expected: {repr(expected_token[:20])}...")
        raise HTTPException(status_code=403, detail="Token invalide")'''

content = content.replace(old_code, new_code)

with open('/opt/Projet_AUTOBOT/src/autobot/v2/api/dashboard.py', 'w') as f:
    f.write(content)

print('✅ Debug ajouté')
