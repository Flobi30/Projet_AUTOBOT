# Phase 4 - Paper Trading AUTOBOT

## Vue d'ensemble

Phase 4 est la validation finale de la stratégie Grid Trading avant le passage en trading réel avec 500€.

### Configuration

| Paramètre | Valeur |
|-----------|--------|
| Symbol | BTC/USDT |
| Capital | 500 USDT (fictif) |
| Grid | 15 niveaux |
| Range | +/-7% (14% total) |
| Durée | 7 jours minimum |
| Mode | PAPIER uniquement |

### Critères de Validation J7

Pour passer en trading réel, les critères suivants doivent être atteints:

| Critère | Seuil |
|---------|-------|
| Win rate | >= 50% |
| Drawdown | <= 20% |
| Profit factor | >= 1.2 |
| Trades minimum | >= 50 |

## Lancement

### Démarrage complet

```bash
cd /home/autobot/Projet_AUTOBOT
python scripts/launch_phase4.py --days 7
```

### Options de lancement

```bash
# Reprendre une session précédente
python scripts/launch_phase4.py --resume

# Durée personnalisée
python scripts/launch_phase4.py --days 14

# Voir le statut actuel
python scripts/launch_phase4.py --status

# Configurer les cron jobs
python scripts/launch_phase4.py --setup-cron
```

## Monitoring 24/7

### Vérification manuelle

```bash
# Statut complet
python scripts/monitoring_daemon.py --status

# Vérification unique
python scripts/monitoring_daemon.py --once

# Mode daemon (continu)
python scripts/monitoring_daemon.py --daemon --interval 600
```

### Configuration Cron (toutes les 10 minutes)

```cron
*/10 * * * * /usr/bin/python3 /home/autobot/Projet_AUTOBOT/scripts/monitoring_daemon.py --once >> /tmp/autobot_monitoring.log 2>&1
```

### Alertes

Le système génère des alertes pour:

| Type | Seuil | Sévérité |
|------|-------|----------|
| Drawdown Warning | >= 15% | WARNING |
| Drawdown Critical | >= 20% | CRITICAL |
| Pertes consécutives | >= 5 | WARNING |
| Taux d'erreur | >= 5% | WARNING |
| Process arrêté | - | CRITICAL |

## Rapports Quotidiens

### Génération manuelle

```bash
# Rapport du jour
python scripts/daily_report_generator.py

# Rapport pour une date spécifique
python scripts/daily_report_generator.py --date 2026-02-05

# Rapport final J7
python scripts/daily_report_generator.py --final --markdown
```

### Configuration Cron (minuit)

```cron
0 0 * * * /usr/bin/python3 /home/autobot/Projet_AUTOBOT/scripts/daily_report_generator.py --markdown >> /tmp/autobot_daily_report.log 2>&1
```

## Structure des Logs

```
logs/
├── papier_trading_YYYYMMDD.json    # Logs quotidiens de trading
├── monitoring_YYYYMMDD.json         # Snapshots de monitoring
├── rapport_quotidien_YYYYMMDD.json  # Rapports quotidiens
├── rapport_quotidien_YYYYMMDD.md    # Rapports Markdown
├── rapport_final_j7_YYYYMMDD.json   # Rapport final
├── rapport_final_j7_YYYYMMDD.md     # Rapport final Markdown
├── paper_trading.pid                # PID du process principal
├── session_info.json                # Informations de session
├── paper_trading_runner.log         # Logs du runner
├── monitoring_daemon.log            # Logs du monitoring
└── daily_report.log                 # Logs des rapports
```

## Coordination avec Kimi

Pour le monitoring toutes les 10 minutes avec Kimi:

```bash
# Obtenir le statut JSON pour Kimi
python scripts/monitoring_daemon.py --status
```

Exemple de sortie:
```json
{
  "status": "running",
  "last_check": "2026-02-05T12:00:00",
  "capital": {
    "initial": 500.0,
    "current": 512.50,
    "pnl": 12.50,
    "roi_percent": 2.5
  },
  "performance": {
    "total_trades": 25,
    "trades_today": 8,
    "win_rate": 56.0,
    "drawdown_percent": 3.2
  },
  "alerts": {
    "active_count": 0,
    "total_count": 0,
    "recent": []
  }
}
```

## Livrables J7

À la fin des 7 jours:

1. **logs/** - Fichiers JSON quotidiens
2. **rapport_final_j7.md** - Rapport final avec décision GO/NO-GO
3. **recommandations_optimisation.md** - Suggestions d'amélioration

## Décision Finale

| Statut | Signification |
|--------|---------------|
| **GO** | Tous les critères validés, prêt pour trading réel |
| **REVIEW** | Majorité des critères validés, révision recommandée |
| **NO-GO** | Critères non atteints, continuer le papier trading |

## Variables d'Environnement

```bash
# API Binance Testnet (optionnel pour simulation pure)
export BINANCE_TESTNET_API_KEY="your_testnet_api_key"
export BINANCE_TESTNET_API_SECRET="your_testnet_api_secret"
```

## Dépannage

### Le process ne démarre pas

```bash
# Vérifier les logs
tail -f logs/paper_trading_runner.log

# Vérifier le PID
cat logs/paper_trading.pid
ps aux | grep python
```

### Pas de trades générés

1. Vérifier que le prix BTC est dans la plage du grid
2. Vérifier les logs pour les erreurs de connexion
3. Vérifier la configuration dans `config/binance_testnet.yml`

### Alertes non reçues

```bash
# Vérifier le monitoring
python scripts/monitoring_daemon.py --status

# Vérifier les logs de monitoring
tail -f logs/monitoring_daemon.log
```
