import re

with open('/opt/Projet_AUTOBOT/dashboard/src/pages/Performance.tsx', 'r') as f:
    content = f.read()

# Fix API_BASE_URL
content = content.replace('http://178.104.0.255:8080', 'http://204.168.205.73:8080')

# Add API_TOKEN if not present
if 'API_TOKEN' not in content:
    content = content.replace(
        "const API_BASE_URL = 'http://204.168.205.73:8080';",
        "const API_BASE_URL = 'http://204.168.205.73:8080';\nconst API_TOKEN = 'un_token_aléatoire_ici';"
    )

# Fix fetch calls - replace the apiFetch function
old_func = '''async function apiFetch<T>(path: string): Promise<T|null> {
  try { const r = await fetch(`${API_BASE_URL}${path}`); return r.ok ? await r.json() : null; } catch { return null; }
}'''

new_func = '''async function apiFetch<T>(path: string): Promise<T|null> {
  try { 
    const r = await fetch(`${API_BASE_URL}${path}`, { 
      headers: { "Authorization": `Bearer ${API_TOKEN}` } 
    }); 
    return r.ok ? await r.json() : null; 
  } catch { 
    return null; 
  }
}'''

content = content.replace(old_func, new_func)

with open('/opt/Projet_AUTOBOT/dashboard/src/pages/Performance.tsx', 'w') as f:
    f.write(content)

print('✅ Performance.tsx corrigé')
