# Audit Opus 4.6 — 2026-04-07

## Etat general
**DEGRADED** — Bot fonctionnel en paper trading, mais plusieurs problemes de securite et de performance identifies.

---

## Resume infrastructure
| Composant | Etat |
|-----------|------|
| Container Docker | UP (healthy), restart=unless-stopped |
| API Dashboard | Tous endpoints 200 OK |
| WebSocket Kraken | Connected (XBT/EUR subscribed) |
| Authentification API | Token Bearer fonctionne (401/403 correctement) |
| Base de donnees SQLite | Fonctionnelle (4 tables: positions, instance_state, trades, sqlite_sequence) |
| Mode trading | Paper Trading uniquement |
| Serveur (CAX11) | CPU 25%, RAM 8.2%, Disk 6% |

---

## Problemes trouves

### CRITICAL

1. **[SECURITE] Port 8080 expose publiquement sans firewall**
   - `docker-compose.yml:25` — `ports: "8080:8080"` bind sur 0.0.0.0
   - `ufw status` = **inactive** — aucun firewall actif
   - L'API est accessible depuis Internet: `curl http://204.168.205.73:8080/health` retourne 200 OK
   - Meme si l'auth Bearer protege les endpoints /api/*, le /health est public et l'API est exposee a des attaques brute-force sur le token
   - **Reproduire:** `curl http://204.168.205.73:8080/health` depuis n'importe ou
   - **Fix:** Activer UFW (`ufw allow 22 && ufw enable`), restreindre 8080 a des IPs specifiques, ou bind sur 127.0.0.1 + reverse proxy Nginx/Caddy avec HTTPS

2. **[SECURITE] Cles API Kraken en clair dans .env sur disque**
   - `.env:1-2` — KRAKEN_API_KEY et KRAKEN_API_SECRET en clair
   - Le fichier est aussi monte en volume Docker (`.env:/app/.env:ro`)
   - **Fix:** Utiliser Docker secrets, HashiCorp Vault, ou au minimum `chmod 600 .env`

3. **[SECURITE] Dashboard en HTTP, pas HTTPS**
   - `dashboard.py` — Log explicite: "Dashboard en HTTP (non chiffre)"
   - Le token Bearer est transmis en clair sur le reseau
   - **Fix:** Configurer DASHBOARD_SSL_CERT et DASHBOARD_SSL_KEY env vars (support SSL deja code dans DashboardServer), ou utiliser Caddy/Nginx en reverse proxy avec Let's Encrypt

### HIGH

4. **[PERF] CPU a 96.7% — boucle principale consomme trop**
   - `ps aux` montre le process Python a 96.7% CPU constant
   - Le bot consomme presque tout le CPU d'un vCPU ARM64 meme sans trades actifs
   - Load average: 0.95 (presque 100% d'un core)
   - **Cause probable:** Boucle WebSocket/tick trop serree, ou `_cold_path_interval` trop bas
   - **Impact:** En production avec plus de paires, le serveur sera sature
   - **Fix:** Profiler le hot path, ajouter des `await asyncio.sleep()` dans la boucle principale, verifier le tick rate WebSocket

5. **[DATA] 28 instance_state orphelines dans SQLite**
   - `instance_state` contient 29 records dont 28 en status "stopped"
   - Ce sont les residus des deploiements/redemarrages precedents
   - Aucun mecanisme de nettoyage automatique
   - **Impact:** Pollution de la DB, potentiellement confusion dans les metriques
   - **Fix:** Ajouter un cleanup au demarrage: `DELETE FROM instance_state WHERE status='stopped' AND updated_at < datetime('now', '-1 day')`

6. **[BUG — RESOLU] /api/paper-trading/summary retournait 500**
   - `dashboard.py:1048` — `NameError: name 'instances' is not defined`
   - **Le code actuel sur le conteneur a ete corrige et fonctionne maintenant (200 OK)**
   - Visible dans les logs Docker a 15:25:37 et 15:25:51 (avant le restart)
   - **Ce bug existait dans une version precedente et a ete fixe dans le deploiement actuel**

### MEDIUM

7. **[ARCH] uptime_seconds retourne null dans /health**
   - `dashboard.py:130` — `status.get('uptime_seconds')` retourne None
   - Le health check montre: `"uptime_seconds": null` meme quand le bot tourne
   - **Cause:** `start_time` n'est pas correctement propage depuis l'orchestrateur
   - **Fix:** Verifier que `orchestrator.get_status()` inclut `start_time` au bon format

8. **[ARCH] /api/capital — available_cash calcule comme 10% fixe du capital**
   - `dashboard.py:886` — `available = total_capital * 0.1`
   - Ce calcul hardcode ne reflete pas le capital reellement disponible
   - **Fix:** Utiliser `orchestrator.get_available_capital()` ou calculer base sur les positions ouvertes

9. **[ARCH] Market selector spin-off trouve 0 marches**
   - Logs: "0 marches disponibles apres analyse" (analyse de 70 paires)
   - Le market selector ne trouve aucun marche pour le spin-off
   - **Impact:** Fonctionnalite spin-off (diversification automatique) inoperante
   - **Fix:** Verifier les criteres de selection, potentiellement trop restrictifs

10. **[ARCH] CORS restreint a localhost seulement**
    - `dashboard.py:83` — Origins: `http://localhost:5173,http://localhost:3000`
    - Aucun acces dashboard depuis l'exterieur possible (meme avec le bon token)
    - **Fix:** Configurer `DASHBOARD_CORS_ORIGINS` avec le domaine de production

11. **[ARCH] Pas de rate limiting sur les endpoints API authentifies**
    - Seul `/health` a un rate limiter (10 req/s par IP)
    - Les endpoints `/api/*` n'ont aucune protection anti-abus
    - **Fix:** Ajouter un middleware de rate limiting global (par IP et par token)

---

## Points positifs

- **Auth Bearer bien implemente** — 401 sans token, 403 avec mauvais token
- **Paper Trading actif** — mode securise, pas de trades reels
- **Adaptive Grid V3 fonctionnel** — SmartRecentering, 9 pair profiles charges
- **Architecture async propre** — uvloop, orchestrateur async, grid strategy bien structuree
- **Health check Docker** — interval 30s, retries 3, start_period 60s
- **Logging structure** — rotation 10MB, 5 backups, JSON format
- **Resource limits Docker** — 3GB RAM, 1.5 CPU max
- **Emergency stop avec confirmation** — CONFIRM_STOP requis
- **Erreurs internes masquees** — les 500 ne leakent pas les details
- **Multi-stage Dockerfile** — frontend build separe, image finale legere
- **Non-root user** dans le container (appuser)

---

## Architecture du code

### dashboard.py (1188 lignes)
- 17 endpoints API au total
- Auth Bearer sur tous les endpoints sauf /health
- Pydantic models pour validation
- Thread-safe via `app.state.orchestrator`
- CORS configure (mais trop restrictif pour production)
- Code propre, bien structure

### grid_async.py (~480 lignes)
- V3 Adaptive Grid avec SmartRecentering
- Lazy loading des modules V3
- Hot path (on_price) CPU-bound, pas d'I/O
- Cold path (adaptive update) toutes les 60 ticks
- Speculative order cache (P6)
- Architecture solide, separation hot/cold path

### main_async.py (~230 lignes)
- Entry point async avec uvloop
- OS tuning (P5)
- PairProfileRegistry charge (9 profiles)
- Signal handlers pour graceful shutdown
- Health reporting toutes les 60s
- Demarrage propre et bien logue

---

## Base de donnees

| Table | Records | Etat |
|-------|---------|------|
| positions | 0 | Vide (normal en paper trading) |
| instance_state | 29 | 28 orphelines (stopped), 1 active |
| trades | 0 | Vide (aucun trade execute) |
| sqlite_sequence | 0 | Vide |

---

## Endpoints API testes

| Endpoint | Status | Temps | Notes |
|----------|--------|-------|-------|
| GET /health | 200 | <50ms | Public, pas d'auth |
| GET /api/status | 200 | <50ms | Auth OK |
| GET /api/capital | 200 | <50ms | Auth OK |
| GET /api/performance/global | 200 | <50ms | Auth OK |
| GET /api/paper-trading/summary | 200 | <50ms | Auth OK (etait 500 avant fix) |
| GET /api/trades | 200 | <50ms | Auth OK, 0 trades |
| GET /api/system | 200 | ~1s | Auth OK (psutil cpu_percent) |
| GET /api/drawdown | 200 | <50ms | Auth OK |
| GET /api/instances | 200 | <50ms | Auth OK, 1 instance |
| NO AUTH test | 401 | - | Correct |
| WRONG TOKEN test | 403 | - | Correct |

---

## Recommandations prioritaires

### Immediat (cette semaine)
1. **ACTIVER LE FIREWALL UFW** et restreindre le port 8080
   ```bash
   ufw default deny incoming
   ufw default allow outgoing
   ufw allow 22/tcp
   ufw allow from YOUR_IP to any port 8080
   ufw enable
   ```
2. **Mettre en place HTTPS** (Caddy reverse proxy + Let's Encrypt)
3. **Securiser .env** — `chmod 600 .env`, envisager Docker secrets
4. **Investiguer la consommation CPU** a 96.7% — profiler le hot path

### Court terme (ce mois)
5. Nettoyer les instance_state orphelines (28 records)
6. Corriger uptime_seconds qui retourne null
7. Ajouter rate limiting sur les endpoints API
8. Configurer CORS pour le domaine de production

### Moyen terme
9. Ajouter monitoring externe (UptimeRobot, Grafana)
10. Implementer les alertes (Telegram/Discord pour trades, erreurs)
11. Backup automatique de la DB SQLite
12. Revoir le market selector pour le spin-off

---

*Audit realise par Opus 4.6 — 2026-04-07 13:29 UTC*
*Serveur: 204.168.205.73 (Hetzner CAX11 ARM64, 2 vCPU, 8GB RAM)*
