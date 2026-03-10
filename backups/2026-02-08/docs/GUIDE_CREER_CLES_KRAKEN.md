# GUIDE - Créer clés API Kraken pour AUTOBOT

## Étape 1: Créer un compte Kraken
1. Va sur https://www.kraken.com/
2. Clique sur "Sign Up" ou "Créer un compte"
3. Remplis tes informations (email, mot de passe)
4. Vérifie ton email
5. Complète la vérification d'identité (KYC)
   - Photo de ta pièce d'identité
   - Selfie
   - Preuve d'adresse (facture EDF, etc.)

⚠️ **Important**: La vérification peut prendre 1-2 jours, mais tu peux déjà créer les clés API avant.

## Étape 2: Activer la 2FA (obligatoire pour API)
1. Dans ton compte Kraken, va dans "Security" ou "Sécurité"
2. Active "2FA" (Two-Factor Authentication)
3. Utilise une app comme Google Authenticator ou Authy
4. Scanne le QR code avec l'app
5. Saisis le code à 6 chiffres pour confirmer

## Étape 3: Créer les clés API
1. Dans ton compte, va dans:
   - "Settings" → "API" 
   - OU "Paramètres" → "API"

2. Clique sur "Generate New Key" ou "Générer une nouvelle clé"

3. Donne un nom à ta clé:
   - Exemple: "AUTOBOT_Trading"

4. **Coche ces permissions** (très important):
   ✅ "Query Funds" (voir les fonds)
   ✅ "Query Closed Orders & Trades" (voir l'historique)
   ✅ "Query Open Orders & Trades" (voir ordres en cours)
   ✅ "Create & Cancel Orders" (créer/annuler ordres)
   
   ❌ NE PAS cocher "Withdraw Funds" (retrait) - trop risqué
   ❌ NE PAS cocher "Deposit Funds" - inutile pour le bot

5. Clique sur "Generate Key"

6. **IMPORTANT**: Note immédiatement ces 2 valeurs:
   - **API Key** (clé publique) - commence par des lettres/chiffres
   - **Private Key** (clé secrète) - longue chaîne de caractères

   ⚠️ **La Private Key ne sera affichée qu'une seule fois!**
   Si tu la perds, tu dois recréer une clé.

## Étape 4: Tester (optionnel mais recommandé)
1. Va dans l'onglet "Funding" ou "Financement"
2. Vérifie que tu as des fonds (même 10€ pour tester)
3. Si pas de fonds, fais un dépôt (SEPA gratuit, 1-2 jours)

## Étape 5: Donner les clés à AUTOBOT
Quand Devin sera prêt, tu devras donner:
- API Key (la clé publique)
- Private Key (la clé secrète)

⚠️ **Ne donne JAMAIS ces clés à quelqu'un d'autre!**
Elles donnent accès à ton compte Kraken.

## Problèmes fréquents

**"Je n'arrive pas à créer de clé API"**
→ Vérifie que la 2FA est activée (obligatoire)

**"La vérification d'identité est longue"**
→ C'est normal (1-2 jours), mais tu peux quand même créer les clés API

**"Je ne comprends pas les permissions"**
→ Coche juste celles listées ci-dessus, ne touche pas aux autres

---
**Besoin d'aide ?** Kraken a un support client en français sur leur site.
