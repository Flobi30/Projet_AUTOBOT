# Sécurité d'AUTOBOT

Ce document décrit les mesures de sécurité mises en place pour protéger l'application AUTOBOT.

## Mesures de sécurité implémentées

### 1. Web Application Firewall (WAF)

Un pare-feu applicatif a été mis en place pour filtrer les requêtes malveillantes. Il détecte et bloque automatiquement:

- Les tentatives d'injection SQL
- Les attaques XSS (Cross-Site Scripting)
- Les tentatives de traversée de chemin (Path Traversal)

Le WAF est implémenté sous forme de middleware FastAPI dans `src/autobot/autobot_security/waf.py`.

### 2. Limitation de taux (Rate Limiting)

Un système de limitation de taux a été mis en place pour prévenir les attaques par force brute, particulièrement sur les endpoints d'authentification:

- Limite de 5 tentatives de connexion par minute par IP (configurable via variables d'environnement)
- Blocage temporaire de 5 minutes après dépassement de la limite
- Protection des endpoints `/login` et `/token`

Le rate limiting est implémenté sous forme de middleware FastAPI dans `src/autobot/autobot_security/rate_limiting.py`.

### 3. Blocage d'IP avec iptables

Un système de blocage d'IP au niveau du système a été mis en place:

- Création d'une chaîne iptables dédiée `AUTOBOT`
- Blocage automatique des IPs détectées comme malveillantes
- Intégration avec le système de surveillance des logs

L'implémentation se trouve dans `src/autobot/autobot_security/ip_blocker.py`.

### 4. Surveillance des logs

Un système de surveillance des logs de sécurité a été implémenté:

- Enregistrement centralisé des événements de sécurité
- Détection des comportements suspects
- Blocage automatique des IPs dépassant un seuil de suspicion
- Exécution dans un thread séparé pour ne pas impacter les performances

L'implémentation se trouve dans `src/autobot/autobot_security/log_monitor.py`.

### 5. Amélioration de la classe AutobotGuardian

La classe AutobotGuardian a été améliorée pour:

- Enregistrer les événements de sécurité
- Maintenir une liste des IPs suspectes
- Écrire les événements dans un fichier de log

## Configuration

Les paramètres de sécurité peuvent être configurés via des variables d'environnement:

| Variable | Description | Valeur par défaut |
|----------|-------------|------------------|
| `AUTOBOT_RATE_LIMIT` | Nombre maximal de requêtes par période | 5 |
| `AUTOBOT_RATE_LIMIT_WINDOW` | Période de temps pour le rate limiting (secondes) | 60 |
| `AUTOBOT_BLOCK_DURATION` | Durée de blocage après dépassement de limite (secondes) | 300 |
| `AUTOBOT_WAF_MAX_STRIKES` | Nombre maximal d'attaques avant blocage permanent | 3 |
| `AUTOBOT_ATTACK_THRESHOLD` | Seuil d'événements suspects avant blocage | 3 |
| `AUTOBOT_LOG_FILE` | Chemin du fichier de log de sécurité | /var/log/autobot/security.log |
| `AUTOBOT_BLOCK_IP` | IP à bloquer automatiquement au démarrage | 187.234.19.188 |

## Vérification de la sécurité

Pour vérifier que les mesures de sécurité fonctionnent correctement:

1. Consultez les logs de sécurité: `tail -f /var/log/autobot/security.log`
2. Vérifiez les règles iptables: `sudo iptables -L AUTOBOT`
3. Testez le rate limiting en effectuant plusieurs tentatives de connexion rapides
4. Vérifiez que l'IP malveillante est bloquée: `sudo iptables -L AUTOBOT | grep 187.234.19.188`

## Maintenance

Pour mettre à jour les règles de sécurité:

1. Modifiez les fichiers dans `src/autobot/autobot_security/`
2. Redémarrez le service: `sudo supervisorctl restart autobot`
