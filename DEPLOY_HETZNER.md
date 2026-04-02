# Deployment Guide — AutoBot V2 on Hetzner

## 🎯 Objectif
Déployer AutoBot V2 sur VPS Hetzner CX11 (ou supérieur) avec Docker.

## 📋 Prérequis
- Compte Hetzner Cloud créé
- Clé SSH générée (`ssh-keygen -t ed25519`)
- Repository GitHub cloné localement

## 🚀 Étape 1 : Créer le Serveur

1. **Hetzner Cloud Console** → Projects → New Project → "AutoBot"
2. **Add Server**:
   - Type: **CX11** (1 vCPU, 2 GB RAM, 20 GB) — 3.79€/mois
   - Image: **Ubuntu 22.04 LTS**
   - Location: Nuremberg (ou Falkenstein)
   - SSH Key: Coller ta clé publique (`cat ~/.ssh/id_ed25519.pub`)
   - Name: `autobot-v2`
3. **Create & Buy**

## 🐳 Étape 2 : Configurer le Serveur

```bash
# Se connecter au serveur
ssh root@<IP_DU_SERVEUR>

# Mise à jour système
apt update && apt upgrade -y

# Installer Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Installer Docker Compose
apt install -y docker-compose

# Créer répertoire projet
mkdir -p /opt/autobot
cd /opt/autobot
```

## 📁 Étape 3 : Copier les Fichiers

```bash
# Depuis ton PC local
scp -r . root@<IP_DU_SERVEUR>:/opt/autobot/

# OU cloner depuis GitHub sur le serveur
git clone https://github.com/Flobi30/Projet_AUTOBOT.git /opt/autobot
cd /opt/autobot
```

## 🔧 Étape 4 : Configuration

```bash
# Créer le fichier .env
cat > /opt/autobot/.env << 'EOF'
# === KRAKEN API (SANDBOX pour paper trading) ===
KRAKEN_API_KEY=votre_cle_sandbox
KRAKEN_API_SECRET=votre_secret_sandbox

# === ENVIRONNEMENT ===
ENV=production
LOG_LEVEL=INFO

# === DASHBOARD ===
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8080
DASHBOARD_API_TOKEN=votre_token_securise_ici

# === TRADING CONFIG ===
INITIAL_CAPITAL=100
MAX_INSTANCES=10
PAPER_TRADING=true
EOF

# Permissions
chmod 600 /opt/autobot/.env
```

## 🚀 Étape 5 : Lancement

```bash
cd /opt/autobot

# Build et lancement
docker-compose up --build -d

# Voir les logs
docker-compose logs -f autobot

# Arrêter
docker-compose down
```

## 📊 Étape 6 : Monitoring

```bash
# Health check
curl http://localhost:8080/health

# Stats
docker stats autobot

# Logs en temps réel
docker-compose logs -f --tail=100
```

## 🔒 Sécurité (IMPORTANT)

```bash
# Firewall UFW
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 8080/tcp  # Dashboard (restreindre à ton IP !)
ufw enable

# Restreindre dashboard à ton IP uniquement
ufw delete allow 8080/tcp
ufw allow from <TON_IP_PERSO> to any port 8080
```

## 🧪 Mode Paper Trading

Par défaut, le bot est en mode paper. Pour vérifier :
```bash
# Dans les logs, chercher :
# "📝 PAPER TRADING MODE — Aucun ordre réel ne sera exécuté"
```

## 🔄 Mises à jour

```bash
cd /opt/autobot
git pull origin master
docker-compose down
docker-compose up --build -d
```

## 🆘 Dépannage

| Problème | Solution |
|----------|----------|
| Container ne démarre pas | `docker-compose logs` |
| Out of memory | Passer à CX21 (4 GB RAM) |
| Disk full | `docker system prune -a` |
| Connexion SSH refusée | Vérifier clé SSH dans console Hetzner |

## 📞 Support
- Logs: `/opt/autobot/logs/`
- Data: `/opt/autobot/data/`
- Backup: `/opt/autobot/data/backups/`
