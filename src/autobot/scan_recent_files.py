import os
import time
from datetime import datetime, timedelta

# Dossier de base à scanner (adapter si nécessaire)
BASE_DIR = "C:/Users/flore/Desktop/Projet_AUTOBOT"
# Nombre de jours à remonter
DAYS = 3
# Extensions à surveiller
EXTENSIONS = (".py", ".json", ".yml", ".yaml", ".txt", ".md")

# Durée de référence
cutoff_time = time.time() - (DAYS * 86400)

print(f"\n📦 Scan des fichiers modifiés/supprimés dans {BASE_DIR} depuis {DAYS} jours...\n")

suspicious = []

for root, dirs, files in os.walk(BASE_DIR):
    for fname in files:
        if fname.endswith(EXTENSIONS):
            full_path = os.path.join(root, fname)
            try:
                stat = os.stat(full_path)
                modified_time = stat.st_mtime
                created_time = stat.st_ctime
                if modified_time >= cutoff_time or created_time >= cutoff_time:
                    suspicious.append((full_path, datetime.fromtimestamp(modified_time)))
            except FileNotFoundError:
                # Fichier supprimé pendant le scan
                continue

if suspicious:
    print(f"🔍 Fichiers trouvés récemment modifiés/créés :\n")
    for path, mtime in sorted(suspicious, key=lambda x: x[1], reverse=True):
        print(f"🗂️  {path} | Modifié le {mtime}")
else:
    print("✅ Aucun fichier suspect détecté récemment.")


