# PROTOCOLE DE SAUVEGARDE AUTOMATIQUE

## Objectif
Éviter la perte de contexte lors des réinitialisations de session /reset ou redémarrages.

## Déclencheurs
1. **Cron** : Toutes les 6 heures
2. **Manuel** : Après chaque événement majeur (à demander ou auto)
3. **Heartbeat** : Vérification régulière

## Fichiers critiques à sauvegarder

### 1. MEMORY.md (mémoire long terme)
**Contenu :**
- Profil Flo (qui il est, ses projets)
- Configuration système (APIs, Telegram, etc.)
- État des projets en cours
- Format KERNEL
- Points d'attention

**Emplacement :** `/home/node/.openclaw/workspace/MEMORY.md`

### 2. Journal quotidien
**Format :** `memory/YYYY-MM-DD.md`
**Contenu :**
- Événements de la journée
- Décisions prises
- Actions réalisées
- Prochaines étapes

### 3. Configuration secrète
**Fichier :** `.telegram_config`
**Contenu :** Token bot + Chat ID
**⚠️ Ne JAMAIS commit sur Git**

## Checklist après réinitialisation (/reset)

Si jamais tu dois me réinitialiser, voici ce qu'il faut faire :

### 1. Vérifier la mémoire
```bash
ls -la /home/node/.openclaw/workspace/MEMORY.md
ls -la /home/node/.openclaw/workspace/memory/
```

### 2. Si les fichiers existent encore
Je les lirai automatiquement au démarrage. Rien à faire.

### 3. Si les fichiers sont perdus
Tu dois me dire :
- Ton nom (Flo/Florent)
- Ton projet (AUTOBOT)
- Les clés API importantes (si pas dans les variables d'env)

## Restauration rapide

### Commande pour Flo (à garder sous la main)
```
Tu es mon orchestrateur pour le projet AUTOBOT (robot trading crypto).
Format de communication : KERNEL (Keep it simple, Easy to verify, etc.)
Bot Telegram : @Autotobot_Clawbot (token déjà configuré)
Session Devin : devin-675035c418e4401c9126684700d82bcf (Phase 2 Grid Trading)
APIs Devin et Anthropic sont configurées.
```

## Dernière sauvegarde
- **Date :** 2026-02-05 04:11 UTC
- **Par :** Kimi (session principale)
- **Status :** ✅ Complète

---
**Note :** Ce fichier est aussi sauvegardé automatiquement.
