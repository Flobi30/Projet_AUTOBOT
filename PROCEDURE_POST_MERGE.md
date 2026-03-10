# 🔒 PROCÉDURE POST-MERGE - AUDIT & RÉPARATION AUTOMATIQUE
**Date création:** 2026-02-06  
**Responsable:** Kimi (OpenClaw)  
**Application:** À chaque merge de PR, SANS EXCEPTION

---

## ⚠️ RÈGLE D'OR

**APRÈS CHAQUE MERGE, AVANT DE DIRE "C'EST BON" :**
1. ✅ Audit général du projet
2. ✅ Test d'exécution réel
3. ✅ Correction immédiate si erreur
4. ✅ Validation finale

---

## 📋 CHECKLIST POST-MERGE (À FAIRE SYSTÉMATIQUEMENT)

### ÉTAPE 1: Vérification immédiate (2 min)
```bash
cd /home/node/.openclaw/workspace/autobot

# 1.1 Récupérer les derniers changements
git pull origin master

# 1.2 Vérifier que les fichiers sont bien là
ls -la scripts/main.py scripts/persistence.py

# 1.3 Vérifier syntaxe Python
python3 -m py_compile scripts/*.py 2>&1 | grep -i error
```

**Si erreur → STOP, corriger immédiatement**

### ÉTAPE 2: Audit général du projet (5 min)
```bash
# 2.1 Lister tous les fichiers Python
find scripts -name "*.py" | wc -l

# 2.2 Vérifier les imports principaux
python3 -c "
import sys
sys.path.insert(0, 'scripts')
sys.path.insert(0, 'src')
try:
    from main import GridTradingBot
    print('✅ main.py import OK')
except Exception as e:
    print(f'❌ main.py: {e}')
    exit(1)
"

# 2.3 Vérifier que les dépendances sont listées
grep -E "^requests|^ccxt" requirements.txt requirements-minimal.txt
```

### ÉTAPE 3: Test d'exécution réel (3 min)
```bash
# 3.1 Test dry-run (sans clés API)
cd scripts
python3 main.py --help 2>&1 | head -20

# 3.2 Test syntaxique complet
python3 test_assembly.py
```

**Si échec → STOP, corriger immédiatement**

### ÉTAPE 4: Audit global (10 min)
- [ ] Double architecture détectée ?
- [ ] Code mort identifié ?
- [ ] Dépendances manquantes ?
- [ ] Fichiers sensibles exposés ?
- [ ] Tests présents et fonctionnels ?

---

## 🔧 PROCÉDURE DE RÉPARATION AUTOMATIQUE

### Quand Kimi détecte une erreur :

**OPTION 1: Correction immédiate (si simple)**
- Corriger le bug directement
- Commiter avec message explicite
- Informer Flo via Telegram

**OPTION 2: Lancer Devin (si complexe)**
- Créer prompt de réparation
- Limiter budget (max 1-2 ACUs)
- Superviser et auditer le résultat

---

## 📝 TEMPLATE RAPPORT POST-MERGE

```markdown
## 🔍 POST-MERGE AUDIT - PR #[NUMÉRO]

**Date:** YYYY-MM-DD HH:MM
**Commit:** [hash]

### ✅ Vérifications rapides
- [ ] Syntaxe Python OK
- [ ] Imports fonctionnent
- [ ] Test assembly passe

### 🔍 Audit général
- Double architecture: [OUI / NON]
- Code mort: [LISTE]
- Dépendances manquantes: [LISTE]

### 🔧 Corrections apportées
- [Correction 1]
- [Correction 2]

### 🎯 Verdict final
- [ ] ✅ Projet stable
- [ ] ⚠️ Corrections mineures faites
- [ ] ❌ Problèmes majeurs détectés
```

---

## 🚨 PLAN D'ACTION IMMÉDIAT (2026-02-06)

### Problèmes identifiés sur PR #51 :

**❌ ERREURS À CORRIGER MAINTENANT :**

1. **Push échoué** - Les corrections sont locales uniquement
   - Action: Configurer auth GitHub ou pousser manuellement

2. **Dépendance circulaire** - grid_calculator.py importe get_price.py
   - Action: Rendre l'import conditionnel

3. **requirements-minimal.txt manquant**
   - Action: Créer avec ccxt + requests

4. **Code mort présent** - 30+ scripts inutilisés
   - Action: Archiver dans dossier `legacy/`

---

## 💡 PROPOSITION: WORKFLOW AUTOMATISÉ

Pour éviter les erreurs futures, je propose :

### 1. Pre-commit hooks
```bash
# Avant chaque commit local
git add -A
git commit -m "message"
# → Hook vérifie syntaxe + imports
```

### 2. Post-merge audit automatique
Après chaque merge GitHub :
- Kimi reçoit webhook
- Exécute audit automatique
- Signale immédiatement si problème

### 3. Correction automatique
Si erreur détectée :
- Kimi corrige si simple (< 5 min)
- Ou lance Devin avec prompt spécifique
- Push correction automatique
- Informe Flo

---

## ✅ ENGAGEMENT

**Je m'engage à :**
1. ✅ Faire un audit post-merge SYSTÉMATIQUEMENT
2. ✅ Ne JAMAIS dire "c'est bon" sans tester
3. ✅ Corriger immédiatement ou lancer Devin
4. ✅ Informer Flo de CHAQUE correction

**Toi tu dois :**
1. Attendre mon audit post-merge avant de considérer que c'est fini
2. Me dire si tu préfères que je corrige moi-même ou que je lance Devin

---

## 🎯 ACTION IMMÉDIATE

**Veux-tu que je :**
1. Corrige les 4 erreurs de PR #51 maintenant ? (push, dépendance, requirements, archivage)
2. Ou lance Devin avec un prompt de nettoyage ?
3. Les deux ?

Réponds par le numéro (1, 2 ou 3)
