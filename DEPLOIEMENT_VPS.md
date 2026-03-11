# Déploiement AUTOBOT V2 - Machine Dédiée / VPS

## 💻 Besoins en Ressources

AUTOBOT V2 est **léger** et ne nécessite pas beaucoup de puissance :

| Ressource | Minimum | Recommandé |
|-----------|---------|------------|
| **CPU** | 1 core | 1-2 cores |
| **RAM** | 512 Mo | 1 Go |
| **Stockage** | 5 Go | 10 Go |
| **Réseau** | Connexion stable | Basse latence vers Kraken |
| **OS** | Linux (Ubuntu/Debian) | Ubuntu 22.04 LTS |

**Coût estimé** : VPS à 3-10€/mois suffit (OVH, Hetzner, DigitalOcean, etc.)

**Pourquoi si peu ?**
- Pas de calcul intensif (pas de ML, pas de minage)
- Juste des appels API et des calculs simples (MA, RSI)
- WebSocket très léger
- SQLite embarqué (pas de serveur BDD)

---

## 🚀 Installation Rapide (Docker)

### 1. Prérequis sur le VPS

```bash
# Connectez-vous à votre VPS
ssh root@votre-ip

# Mettez à jour le système
apt update && apt upgrade -y

# Installez Docker et Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Activez Docker au démarrage
systemctl enable docker
systemctl start docker

# Installez docker-compose
apt install -y docker-compose

# Vérifiez l'installation
docker --version
docker-compose --version
```

### 2. Déployez AUTOBOT

```bash
# Créez un répertoire
mkdir -p /opt/autobot
cd /opt/autobot

# Clonez le repo (ou copiez les fichiers)
git clone https://github.com/Flobi30/Projet_AUTOBOT.git .

# Créez le fichier de configuration
cp .env.example .env
nano .env  # Éditez avec vos clés API
```

**Contenu du fichier .env :**
```bash
# Clés API Kraken (obligatoire)
KRAKEN_API_KEY=votre_clé_api
KRAKEN_API_SECRET=votre_secret_api

# Token pour le dashboard (optionnel mais recommandé)
DASHBOARD_API_TOKEN=un_token_aléatoire_très_long
```

### 3. Démarrez le bot

```bash
# Construisez et démarrez
docker-compose up -d

# Vérifiez que tout fonctionne
docker-compose ps
docker-compose logs -f autobot

# Testez le health check
curl http://localhost:8080/health
```

### 4. Accédez au dashboard

Depuis votre ordinateur local :
```bash
# Créez un tunnel SSH vers le dashboard
ssh -L 3000:localhost:3000 -N -f root@votre-ip
```

Puis ouvrez : http://localhost:3000

**OU** exposez le dashboard publiquement (avec mot de passe !) :
```bash
# Éditez docker-compose.yml
# Changez les ports et ajoutez un reverse proxy nginx
```

---

## 🔧 Commandes Utiles

### Gestion du bot

```bash
# Démarrer
docker-compose up -d

# Arrêter
docker-compose down

# Redémarrer
docker-compose restart

# Voir les logs
docker-compose logs -f autobot
docker-compose logs -f dashboard

# Mise à jour (après git pull)
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Monitoring

```bash
# Utilisation des ressources
docker stats

# Espace disque
df -h

# Mémoire
free -h

# Logs en temps réel
tail -f /opt/autobot/logs/autobot.log
```

---

## 🛡️ Sécurité

### 1. Pare-feu (UFW)

```bash
# Installez UFW
apt install -y ufw

# Par défaut : tout bloquer
ufw default deny incoming
ufw default allow outgoing

# Autoriser SSH
ufw allow 22/tcp

# Autoriser le dashboard (si exposé publiquement)
# ufw allow 3000/tcp  # Dashboard
# ufw allow 8080/tcp  # API (à protéger !)

# Activez
ufw enable
```

### 2. Authentification Dashboard

**Obligatoire** en production :
```bash
# Dans .env
DASHBOARD_API_TOKEN=$(openssl rand -hex 32)
```

### 3. HTTPS avec Nginx (optionnel)

Si vous exposez le dashboard sur Internet :

```bash
# Installez Nginx et Certbot
apt install -y nginx certbot python3-certbot-nginx

# Config Nginx
nano /etc/nginx/sites-available/autobot
```

```nginx
server {
    listen 443 ssl;
    server_name autobot.votredomaine.com;

    ssl_certificate /etc/letsencrypt/live/autobot.votredomaine.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/autobot.votredomaine.com/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
# Activez
ln -s /etc/nginx/sites-available/autobot /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# SSL
certbot --nginx -d autobot.votredomaine.com
```

---

## 📊 Monitoring Automatique

### Health Check Docker

Déjà configuré dans `docker-compose.yml` :
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### Script de vérification

```bash
# Créez /opt/autobot/check-health.sh
#!/bin/bash
HEALTH=$(curl -s http://localhost:8080/health | grep -o '"status":"healthy"')
if [ -z "$HEALTH" ]; then
    echo "$(date): AUTOBOT UNHEALTHY - Restarting..." >> /var/log/autobot-health.log
    docker-compose -f /opt/autobot/docker-compose.yml restart
fi
```

```bash
chmod +x /opt/autobot/check-health.sh
# Ajoutez au crontab pour vérifier toutes les 5 minutes
*/5 * * * * /opt/autobot/check-health.sh
```

---

## 🔄 Mises à Jour

```bash
cd /opt/autobot

# Sauvegarde
cp -r data data.backup.$(date +%Y%m%d)

# Mettez à jour le code
git pull

# Reconstruisez et redémarrez
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Vérifiez
docker-compose ps
docker-compose logs -f --tail=100
```

---

## 🆘 Dépannage

### Le bot ne démarre pas

```bash
# Vérifiez les logs
docker-compose logs autobot

# Vérifiez la config
cat .env | grep -v SECRET  # Masque les secrets

# Testez les clés API
python src/autobot/v2/tests/test_kraken_api.py
```

### Le dashboard n'affiche pas les données

```bash
# Vérifiez que l'API répond
curl http://localhost:8080/health
curl http://localhost:8080/api/status

# Vérifiez les logs
docker-compose logs dashboard
```

### Problèmes de ressources

```bash
# Vérifiez l'utilisation
docker stats --no-stream

# Si manque de RAM
# Ajoutez du swap
fallocate -l 1G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
```

---

## 📞 Support

En cas de problème :
1. Vérifiez les logs : `docker-compose logs -f`
2. Testez la connexion API Kraken : `python src/autobot/v2/tests/test_kraken_api.py`
3. Vérifiez le health check : `curl http://localhost:8080/health`

---

**Votre bot tourne 24/7 sur un VPS à 5€/mois !** 🚀
