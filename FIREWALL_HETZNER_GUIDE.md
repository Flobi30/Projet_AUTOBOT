# Guide Firewall Hetzner — Étape par Étape

## 🎯 Objectif
Créer un firewall qui laisse passer :
- ✅ SSH (port 22) — pour te connecter au serveur
- ✅ Dashboard (port 8080) — pour voir ton bot
- ❌ Tout le reste — bloqué pour la sécurité

---

## 📍 Étape 1 : Créer le Firewall

Dans la console Hetzner Cloud :

1. Menu de gauche → **Firewalls**
2. Bouton bleu **"Add Firewall"**
3. Nom : `autobot-firewall`
4. Description : `Firewall pour AutoBot V2 - SSH + Dashboard uniquement`

---

## 📍 Étape 2 : Règles INBOUND (Entrantes)

Clique sur **"Add Rule"** pour chaque règle :

### Règle 1 — SSH (Connexion au serveur)
```
Protocol: TCP
Port: 22
Source: YOUR_IP/32  ← Mets ton IP publique ici !
Description: SSH access
```

**Comment trouver ton IP :**
- Va sur https://whatismyipaddress.com/
- Copie l'IPv4 (ex: 203.0.113.42)
- Mets : `203.0.113.42/32`

### Règle 2 — Dashboard (Interface web)
```
Protocol: TCP
Port: 8080
Source: YOUR_IP/32  ← Même IP que SSH
Description: AutoBot Dashboard
```

### Règle 3 — ICMP (Ping pour diagnostics)
```
Protocol: ICMP
Source: Any
Description: Ping diagnostics
```

---

## 📍 Étape 3 : Règles OUTBOUND (Sortantes)

Par défaut : **Tout autorisé** ✅

Ne change rien — le bot doit pouvoir appeler :
- Kraken API (HTTPS)
- Docker Hub (téléchargement images)
- Mises à jour Ubuntu

---

## 📍 Étape 4 : Appliquer au Serveur

1. Retourne dans **"Projects"** → ton projet AutoBot
2. Clique sur ton serveur `autobot-v2`
3. Onglet **"Firewalls"**
4. Bouton **"Attach Firewall"**
5. Sélectionne : `autobot-firewall`
6. **Attach**

---

## ✅ Vérification

Après 30 secondes, test :

```bash
# Depuis ton PC
ssh root@<IP_DU_SERVEUR>
# Doit fonctionner (si ton IP est bonne)

# Depuis un autre réseau (4G par exemple)
ssh root@<IP_DU_SERVEUR>
# Doit être REFUSÉ (timeout)
```

---

## 🆘 Si tu te bloques

**Problème :** Tu as mis une mauvaise IP et tu ne peux plus te connecter.

**Solution :**
1. Console Hetzner → Serveur → **"Rescue"** mode
2. Ou via l'API : désactiver temporairement le firewall
3. Ou ajouter une nouvelle règle avec ta nouvelle IP

---

## 📝 Récap Visuel

```
┌─────────────────────────────────────────┐
│         FIREWALL HETZNER                │
├─────────────────────────────────────────┤
│ INBOUND (Ce qui entre sur le serveur)   │
├─────────────────────────────────────────┤
│ ✅ TCP 22   →  TON_IP/32   (SSH)       │
│ ✅ TCP 8080 →  TON_IP/32   (Dashboard) │
│ ✅ ICMP     →  Any         (Ping)      │
│ ❌ Tout le reste → BLOQUÉ              │
├─────────────────────────────────────────┤
│ OUTBOUND (Ce qui sort du serveur)       │
├─────────────────────────────────────────┤
│ ✅ TOUT AUTORISÉ                        │
└─────────────────────────────────────────┘
```

**Tu as compris ?** Besoin d'aide pour trouver ton IP ? 🎯
