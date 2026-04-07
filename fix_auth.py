import re

# Corriger LiveTrading.tsx
with open('LiveTrading.tsx', 'r') as f:
    content = f.read()

# Ajouter API_TOKEN si pas présent
if 'API_TOKEN' not in content:
    content = content.replace(
        "const API_BASE_URL = 'http://204.168.205.73:8080';",
        "const API_BASE_URL = 'http://204.168.205.73:8080';\nconst API_TOKEN = 'un_token_aléatoire_ici';"
    )

# Ajouter headers aux fetch
content = content.replace(
    'await fetch(`${API_BASE_URL}/api/status`)',
    'await fetch(`${API_BASE_URL}/api/status`, { headers: { "Authorization": `Bearer ${API_TOKEN}` } })'
)
content = content.replace(
    'await fetch(`${API_BASE_URL}/api/instances`)',
    'await fetch(`${API_BASE_URL}/api/instances`, { headers: { "Authorization": `Bearer ${API_TOKEN}` } })'
)
content = content.replace(
    'await fetch(`${API_BASE_URL}/api/instances/${firstInstanceId}/positions`)',
    'await fetch(`${API_BASE_URL}/api/instances/${firstInstanceId}/positions`, { headers: { "Authorization": `Bearer ${API_TOKEN}` } })'
)

with open('LiveTrading.tsx', 'w') as f:
    f.write(content)
print('✅ LiveTrading.tsx corrigé')

# Corriger Backtest.tsx
with open('Backtest.tsx', 'r') as f:
    content = f.read()

if 'API_TOKEN' not in content:
    content = content.replace(
        "const API_BASE_URL = 'http://204.168.205.73:8080';",
        "const API_BASE_URL = 'http://204.168.205.73:8080';\nconst API_TOKEN = 'un_token_aléatoire_ici';"
    )

content = content.replace(
    'await fetch(`${API_BASE_URL}/api/capital`)',
    'await fetch(`${API_BASE_URL}/api/capital`, { headers: { "Authorization": `Bearer ${API_TOKEN}` } })'
)

with open('Backtest.tsx', 'w') as f:
    f.write(content)
print('✅ Backtest.tsx corrigé')
