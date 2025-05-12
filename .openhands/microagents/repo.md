## 1. Contexte  
Ce dépôt **AUTOBOT** est un système de trading algorithmique multi-actifs (crypto, forex, actions), e-commerce et IA auto-optimisant, scalable et autonome. Il comprend déjà :  
- Un backend Python/FastAPI (`src/autobot/`)  
- Des modules providers (CCXT, AlphaVantage, CoinGecko, FRED, Shopify, NewsAPI, TwelveData)  
- Des scripts d’initialisation (`bootstrap_full.py`, `validate_all.py`, `full_pipeline.py`)  
- 30+ microagents IA partiellement intégrés (`agents_shortlist.json`)  
- Des tests unitaires de base et une fonctionnalité RL partielle  

## 2. Objectif  
Réaliser, à partir de cet existant, un système **AUTOBOT** complet, robuste et prêt à la production, qui :  
1. S’auto-optimise et s’auto-corrige  
2. Offre un **dashboard web** (Next.js + Tailwind) et une **app mobile** (Flutter ou React Native)  
3. Expose des endpoints FastAPI fonctionnels (/predict, /train, /backtest, /monitoring)  
4. Intègre une boucle RL stable-baselines3 avec tests automatisés  
5. Gère l’arbitrage, la duplication/ghosting d’instances, le réinvestissement et la licence par clé  
6. Est conteneurisé (Docker multi-stage), prêt pour CI/CD et Kubernetes  
7. Livrable en 1 clic (exécutable .exe/.sh/.app + archive portable)  
8. Documenté (README, docs/*) et testé (pytest, coverage, lint)

## 3. Contraintes essentielles  
- **Pas de nouveau dépôt** : refactorer et optimiser l’existant  
- **Tous les tests** (unitaires, RL-mock, smoke-tests HTTP) doivent passer  
- Supprimer **uniquement** ce qui est mort  
- Respecter les conventions Git (`feat:`, `fix:`, `chore:`)  
- Chaque commit doit avoir un message clair et descriptif  

## 4. Tâches détaillées  

### 4.1 Audit & Refactoring  
1. Lister la structure actuelle, points forts/faibles  
2. Supprimer doublons et fichiers inutiles  
3. Corriger imports, noms incohérents, `__init__.py`  
4. Restructurer modules si nécessaire  

### 4.2 Backend FastAPI  
1. Finaliser `/predict`, `/train`, `/backtest`, `/monitoring`  
2. Ajouter validation des entrées et gestion des erreurs  
3. Configurer mocks si clés API manquantes  
4. Écrire tests unitaires pour chaque endpoint  

### 4.3 Reinforcement Learning  
1. Intégrer un test gym CartPole + stable-baselines3  
2. Ajouter script `rl_test.py` et le valider  
3. Documenter les métriques et la configuration  

### 4.4 Duplication & Ghosting  
1. Créer un moteur configurable de duplication d’instances  
2. Ajouter contrôle granulaire du nombre d’instances par clé utilisateur  
3. Écrire tests unitaires de scalabilité  

### 4.5 Frontend Web & Mobile  
1. Next.js + Tailwind : pages Dashboard, Compte, Shopify, Sentiment, Macro, Tech, Settings, Login  
2. Hooks API, composants réutilisables (`Card`, `Table`, `Chart`)  
3. Responsive (mobile-first, breakpoints sm/md/lg)  
4. Flutter/React Native : mêmes écrans, navigation, stockage JWT  

### 4.6 Authentification & Licence  
1. Générer et valider des clés utilisateur  
2. UI desktop + mobile pour gestion des clés et API  
3. Refuser tout accès sans licence valide  

### 4.7 DevOps & CI/CD  
1. Dockerfile multi-étape + `docker-compose.yml`  
2. Workflow GitHub Actions (`ci.yml`) : lint, tests, build, push  
3. Chart Helm minimal pour Kubernetes  
4. Pre-commit (black, isort, flake8)  

### 4.8 Documentation & Veille  
1. `README.md` : Prérequis, Installation, Usage, Backtest, Déploiement, Licence  
2. `docs/architecture.md`, `docs/usage.md`, `docs/enrichments.txt`  
3. Documenter chaque intégration issue de la veille technologique  

## 5. Veille technologique  
En parallèle, rechercher et intégrer :  
- Nouveaux modèles LLM et RL légers  
- Outils de monitoring (Prometheus, Grafana)  
- Pratiques de sécurité et observabilité  
- APIs ou librairies utiles, sans duplication  

## 6. Format de sortie  
- **Commits atomiques**, clairs, préfixés (`feat:`, `fix:`, `chore:`)  
- Chaque fichier généré doit être listé avec son chemin  
- Rapport final : résumé des changements, couverture tests, performances RL  

---