# 📸 Captures d'écran du Dashboard AutoBot V2

## Page 1: Live Trading 📈

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🖥️ SIDEBAR                              │  📈 LIVE TRADING              ● En cours│
│                                          │  Performances en temps réel ● WebSocket │
│  🤖 AUTOBOT                              │                                           │
│  ● LIVE                                  │  ┌──────────────┬──────────────┬────────┐ │
│                                          │  │ 💰 Capital   │ 📈 P&L       │ 🎯 Inst│ │
│  ────────────────────────────            │  │              │              │        │ │
│  TRADING & ANALYSE                       │  │ 5,420.00 €   │ +156.80€     │   12   │ │
│  📈 Live Trading ◄─── ACTIVE             │  │ +156.80€     │ +2.98%       │ 3 strat│ │
│  📊 Backtest                             │  └──────────────┴──────────────┴────────┘ │
│                                          │                                           │
│  ────────────────────────────            │  ┌─────────────────────────────────────┐  │
│  GESTION                                 │  │  📊 ÉVOLUTION DU PORTEFEUILLE        │  │
│  💰 Capital                              │  │                                      │  │
│  📈 Analytics                            │  │    5,420.00 €  +156.80€ (+2.98%)   │  │
│                                          │  │                                      │  │
│  ────────────────────────────            │  │    ▁▂▃▅▆▇█▇▆ (graphique 24h)       │  │
│  SYSTÈME                                 │  │                                      │  │
│  🏥 Diagnostic                           │  └─────────────────────────────────────┘  │
│                                          │                                           │
│  ┌─────────────────────────┐             │  ┌───────────────┬──────────────────┐    │
│  │ ⚡ Bot Status   ACTIF   │             │  │ ⚡ POSITIONS   │ 📋 JOURNAL       │    │
│  │ Performance: +8.42%     │             │  │    OUVERTES    │   D'ACTIVITÉ     │    │
│  └─────────────────────────┘             │  │                │                  │    │
│                                          │  │ BTC/EUR [LONG] │ Position BTC...  │    │
└──────────────────────────────────────────┘  │ +45.20€ +2.15% │ 14:32           │    │
                                              │                │                  │    │
                                              │ ETH/EUR [SHORT]│ Grid #7...       │    │
                                              │ -12.50€ -0.85% │ 14:28           │    │
                                              │                │                  │    │
                                              └───────────────┴──────────────────┘    │
                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Éléments visuels:
- **Fond**: `bg-gray-900` (#111827) - très sombre
- **Cartes**: Dégradé de gray-800 à gray-800/80 avec bordure gray-700/50
- **Coins**: `rounded-2xl` (16px) ou `rounded-xl` (12px)
- **Accent**: Emerald-500 (#10B981) - vert brillant
- **Typographie**: Inter, titres en gras blanc, texte secondaire gray-400
- **Badges**: Fond semi-transparent avec texte coloré

---

## Page 2: Diagnostic 🏥

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🖥️ SIDEBAR                              │  🏥 DIAGNOSTIC SYSTÈME     [🟢 OK] [🔄]│
│                                          │  Dernière mise à jour: 03/04/2025 01:10 │
│  🤖 AUTOBOT                              │                                           │
│  ● LIVE                                  │  ┌──────────────┬──────────────┬────────┐ │
│                                          │  │ 🧠 RAM       │ ⚡ CPU       │ 💾 Disk│ │
│  ────────────────────────────            │  │              │              │        │ │
│  TRADING & ANALYSE                       │  │    45%       │    23%       │   32%  │ │
│  📈 Live Trading                         │  │ [████░░░░░░] │ [██░░░░░░░░] │ [███░░░│ │
│  📊 Backtest                             │  │    🟢 OK     │    🟢 OK     │   🟢 OK│ │
│                                          │  │  4GB total   │  2vCPU ARM   │ 40GB+10│ │
│  ────────────────────────────            │  └──────────────┴──────────────┴────────┘ │
│  GESTION                                 │                                           │
│  💰 Capital                              │  ┌──────────────┬──────────────┬────────┐ │
│  📈 Analytics                            │  │ 🐳 Docker    │ 🌐 Kraken    │ 🗄️ DB  │ │
│                                          │  │              │              │        │ │
│  ────────────────────────────            │  │    🟢 Up     │    🟢 Up     │   🟢 Up│ │
│  SYSTÈME                                 │  │  2 conteneurs│ Lat: 145ms   │ 12.5 MB│ │
│  🏥 Diagnostic ◄─── ACTIVE               │  │ autobot-v2   │ HTTPS OK     │ SQLite │ │
│                                          │  │   running    │ Sandbox Mode │ Backup │ │
│  ┌─────────────────────────┐             │  └──────────────┴──────────────┴────────┘ │
│  │ ⚡ Bot Status   ACTIF   │             │                                           │
│  │ Performance: +8.42%     │             │  ┌─────────────────────────────────────┐  │
│  └─────────────────────────┘             │  │  📈 HISTORIQUE 24H                  │  │
│                                          │  │                                     │  │
└──────────────────────────────────────────┘  │    RAM%  ████ CPU%  ██  Latency    │  │
                                              │    (graphique linéaire multicourbe) │  │
                                              │                                     │  │
                                              └─────────────────────────────────────┘  │
                                                                                      │
                                              ┌─────────────────────────────────────┐  │
                                              │  🟢 TOUT FONCTIONNE PARFAITEMENT    │  │
                                              │  Aucun problème détecté sur le sys. │  │
                                              └─────────────────────────────────────┘  │
                                                                                      │
                                              ┌─────────────────────────────────────┐  │
                                              │  💡 RECOMMANDATIONS                 │  │
                                              │  • Aucune action requise            │  │
                                              │  • Le système fonctionne bien !     │  │
                                              └─────────────────────────────────────┘  │
                                                                                      │
                                              ┌─────────────────────────────────────┐  │
                                              │  ⚡ ACTIONS RAPIDES                 │  │
                                              │  [Voir logs] [Redémarrer] [Backup]  │  │
                                              └─────────────────────────────────────┘  │
                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Différences avec Live Trading:
- **Métriques**: Jauges de progression au lieu de valeurs simples
- **Services**: Cartes de statut avec indicateurs up/down
- **Couleurs d'état**: 🟢 Vert (<80%), 🟡 Orange (80-90%), 🔴 Rouge (>90%)
- **Alertes**: Panneau dédié pour problèmes/recommandations

---

## Page 3: Backtest 🧪

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🖥️ SIDEBAR                              │  🧪 BACKTEST                            │
│                                          │  Tester les stratégies sur l'historique │
│  🤖 AUTOBOT                              │                                           │
│  ● LIVE                                  │  ┌─────────────────────────────────────┐  │
│                                          │  │  📊 PARAMÈTRES DU BACKTEST          │  │
│  ────────────────────────────            │  │                                     │  │
│  TRADING & ANALYSE                       │  │  Stratégie: [Grid Trading ▼]        │  │
│  📈 Live Trading                         │  │  Paire:     [BTC/EUR ▼]             │  │
│  📊 Backtest ◄─── ACTIVE                 │  │  Période:   [Derniers 30 jours ▼]   │  │
│                                          │  │  Capital:   [1000 €]                │  │
│  ────────────────────────────            │  │                                     │  │
│  GESTION                                 │  │        [🚀 LANCER LE BACKTEST]      │  │
│  💰 Capital                              │  └─────────────────────────────────────┘  │
│  📈 Analytics                            │                                           │
│                                          │  ┌─────────────────────────────────────┐  │
│  ────────────────────────────            │  │  📈 RÉSULTATS RÉCENTS               │  │
│  SYSTÈME                                 │  │                                     │  │
│  🏥 Diagnostic                           │  │  Grid - BTC/EUR    PF: 2.34  ✅    │  │
│                                          │  │  01/03 - 31/03    +234€ (+23.4%)   │  │
│  ┌─────────────────────────┐             │  │                                     │  │
│  │ ⚡ Bot Status   ACTIF   │             │  │  Trend - ETH/EUR   PF: 1.89  ✅    │  │
│  │ Performance: +8.42%     │             │  │  15/03 - 31/03    +189€ (+18.9%)   │  │
│  └─────────────────────────┘             │  │                                     │  │
│                                          │  │  MeanRev - BTC/EUR PF: 1.12  ⚠️    │  │
└──────────────────────────────────────────┘  │  01/03 - 15/03    +12€  (+1.2%)    │  │
                                              └─────────────────────────────────────┘  │
                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Page 4: Capital 💰

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🖥️ SIDEBAR                              │  💰 GESTION DU CAPITAL                  │
│                                          │  Répartition et allocations             │
│  🤖 AUTOBOT                              │                                           │
│  ● LIVE                                  │  ┌──────────────────┬────────────────┐  │
│                                          │  │  💰 TOTAL        │  📊 ALLOCATIONS │  │
│  ────────────────────────────            │  │                  │                 │  │
│  TRADING & ANALYSE                       │  │   5,420.00 €     │   [camembert]   │  │
│  📈 Live Trading                         │  │                  │                 │  │
│  📊 Backtest                             │  │   +156.80 €      │   Grid: 40%     │  │
│                                          │  │   (+2.98%)       │   Trend: 35%    │  │
│  ────────────────────────────            │  │                  │   MeanRev: 25%  │  │
│  GESTION                                 │  └──────────────────┴────────────────┘  │
│  💰 Capital ◄─── ACTIVE                  │                                           │
│  📈 Analytics                            │  ┌─────────────────────────────────────┐  │
│                                          │  │  📋 INSTANCES PAR STRATÉGIE         │  │
│  ────────────────────────────            │  │                                     │  │
│  SYSTÈME                                 │  │  Grid #1    500€    +23€   🟢      │  │
│  🏥 Diagnostic                           │  │  Grid #2    400€    +18€   🟢      │  │
│                                          │  │  Trend #1   600€    +45€   🟢      │  │
│  ┌─────────────────────────┐             │  │  Trend #2   500€    -12€   🔴      │  │
│  │ ⚡ Bot Status   ACTIF   │             │  │  MeanRev #1 300€    +8€    🟢      │  │
│  │ Performance: +8.42%     │             │  │  ...                               │  │
│  └─────────────────────────┘             │  └─────────────────────────────────────┘  │
│                                          │                                           │
└──────────────────────────────────────────┘                                           │
                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Page 5: Analytics 📊

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🖥️ SIDEBAR                              │  📊 ANALYTICS                           │
│                                          │  Métriques de performance               │
│  🤖 AUTOBOT                              │                                           │
│  ● LIVE                                  │  ┌──────────┬──────────┬──────────┐     │
│                                          │  │ Profit   │  Sharpe  │  Win     │     │
│  ────────────────────────────            │  │ Factor   │  Ratio   │  Rate    │     │
│  TRADING & ANALYSE                       │  │          │          │          │     │
│  📈 Live Trading                         │  │   2.34   │   1.89   │   68%    │     │
│  📊 Backtest                             │  │   🟢     │   🟢     │   🟢     │     │
│                                          │  └──────────┴──────────┴──────────┘     │
│  ────────────────────────────            │                                           │
│  GESTION                                 │  ┌──────────┬──────────┬──────────┐     │
│  💰 Capital                              │  │ Max      │  Current │  Trades  │     │
│  📈 Analytics ◄─── ACTIVE                │  │ Drawdown │  P&L     │  Total   │     │
│                                          │  │          │          │          │     │
│  ────────────────────────────            │  │   -8%    │  +156€   │   156    │     │
│  SYSTÈME                                 │  │   🟢     │   🟢     │          │     │
│  🏥 Diagnostic                           │  └──────────┴──────────┴──────────┘     │
│                                          │                                           │
│  ┌─────────────────────────┐             │  ┌─────────────────────────────────────┐  │
│  │ ⚡ Bot Status   ACTIF   │             │  │  📈 PERFORMANCE PAR STRATÉGIE       │  │
│  │ Performance: +8.42%     │             │  │                                     │  │
│  └─────────────────────────┘             │  │  [graphique comparatif]             │  │
│                                          │  │                                     │  │
└──────────────────────────────────────────┘  │  Grid    ████████████  PF: 2.45    │  │
                                              │  Trend   ██████████    PF: 1.92    │  │
                                              │  MeanRev ██████        PF: 1.23    │  │
                                              └─────────────────────────────────────┘  │
                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎨 Palette de couleurs

| Élément | Couleur | Code |
|---------|---------|------|
| Fond principal | Gray 900 | `#111827` |
| Sidebar | Gray 800 | `#1F2937` |
| Cartes | Dégradé Gray 800 → 800/80 | - |
| Bordures | Gray 700/50 | `rgba(55, 65, 81, 0.5)` |
| Accent principal | Emerald 500 | `#10B981` |
| Succès | Emerald 400 | `#34D399` |
| Avertissement | Yellow 400 | `#FBBF24` |
| Erreur | Red 400 | `#F87171` |
| Texte principal | Blanc | `#FFFFFF` |
| Texte secondaire | Gray 400 | `#9CA3AF` |

## 📐 Dimensions

- **Sidebar**: 256px de large
- **Bordures arrondies**: 
  - `rounded-2xl` = 16px (grandes sections)
  - `rounded-xl` = 12px (cartes)
  - `rounded-lg` = 8px (boutons, badges)
- **Espacement**: 
  - Padding page: 32px (p-8)
  - Gap entre cartes: 24px (gap-6)
  - Padding cartes: 24px (p-6)
