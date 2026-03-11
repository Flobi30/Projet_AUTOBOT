# 🔬 AUDIT SPÉCIALISÉ — Logique de Trading & Mathématiques Financières
## AUTOBOT V2 — Rapport Complet
**Date:** 2026-03-11 | **Auditeur:** Subagent spécialisé Trading/Math

---

## TABLE DES MATIÈRES
1. [Anomalies Mathématiques](#1---anomalies-mathématiques)
2. [Biais de Trading Identifiés](#2---biais-de-trading-identifiés)
3. [Analyse de Rentabilité](#3---analyse-de-rentabilité)
4. [Scénarios de Risque](#4---scénarios-de-risque)
5. [Suggestions d'Amélioration](#5---suggestions-damélioration)

---

## 1 — 🚨 ANOMALIES MATHÉMATIQUES

### 🚨 CRITIQUE — `calculate_grid_levels()` : Grille NON-symétrique (BIAIS FONDAMENTAL)

**Fichier:** `strategies/__init__.py`, lignes ~190-210

```python
half_range = range_percent / 2     # ex: 7/2 = 3.5
step = range_percent / (num_levels - 1)  # ex: 7/14 = 0.5
for i in range(num_levels):
    offset = -half_range + (i * step)    # -3.5, -3.0, …, +3.5
    level_price = center_price * (1 + offset / 100)
```

**Problème:** La formule applique des offsets **additifs en pourcentage**, ce qui crée une **asymétrie logarithmique**.

- Level bas : `center × (1 − 3.5/100)` = `center × 0.965`
- Level haut : `center × (1 + 3.5/100)` = `center × 1.035`

L'écart absolu est identique (+/-3.5% du centre), mais **en trading, les mouvements de prix sont multiplicatifs**. Une baisse de 3.5% suivie d'une hausse de 3.5% ne ramène PAS au prix initial :
- `100 × 0.965 × 1.035 = 99.8775` → **perte de 0.12%** par cycle complet

**Impact concret avec 15 niveaux:** Après un aller-retour complet bas→haut, le bot perd environ `15 × 0.12% / 2 ≈ 0.9%` en biais structurel, **avant même les frais**.

**Sévérité:** 🟡 MOYENNE — L'impact est faible sur un range de ±3.5%, mais s'accumule sur de nombreux cycles et s'aggrave avec des ranges plus larges.

**Correction recommandée:** Utiliser des niveaux **géométriques** :
```python
ratio = (1 + range_percent/100) ** (1 / (num_levels - 1))
levels = [center_price * ratio**(i - (num_levels-1)/2) for i in range(num_levels)]
```

---

### 🚨 CRITIQUE — Grid: `get_current_capital()` retourne le capital TOTAL, pas le disponible

**Fichier:** `grid.py`, `on_price()` ligne ~183 et `_init_grid()` ligne ~76

```python
available_capital = self.instance.get_current_capital()  # ← TOTAL, inclut allocated!
```

Or dans `instance.py` :
```python
def get_current_capital(self) -> float:
    """Capital courant (total, incluant alloué dans positions)"""
    return self._current_capital
```

Et il existe `get_available_capital()` :
```python
def get_available_capital(self) -> float:
    """Capital disponible = Capital total - Capital alloué"""
    return self._current_capital - self._allocated_capital
```

**Problème:** La grille utilise `get_current_capital()` (total) pour calculer `_runtime_capital_per_level` et pour `_can_open_position()`. Cela signifie que :

1. Au démarrage avec 0 positions : OK (available = total)
2. Après des achats : le bot **croit** avoir plus de capital disponible qu'il n'en a réellement
3. `_can_open_position()` compare `available_capital` (qui est en fait le total) à `capital_per_level`, ce qui **surestime** la capacité d'achat

La marge de 90% (`usable_capital = available * 0.90`) masque partiellement ce bug, mais avec 10 positions ouvertes, le calcul devient significativement faux.

**Sévérité:** 🔴 HAUTE — Peut causer des achats quand le capital réellement disponible est insuffisant, menant à des ordres rejetés par l'exchange ou un dépassement de budget.

**Correction:** Remplacer `get_current_capital()` par `get_available_capital()` dans `on_price()` de la grille.

---

### 🚨 MODÉRÉ — Grid: `_calculate_dynamic_capital_per_level()` ignore le paramètre

```python
def _calculate_dynamic_capital_per_level(self, available_capital: Optional[float] = None) -> float:
    # Guard check on available_capital
    ...
    # Retourne la valeur calculée à l'initialisation
    return self._runtime_capital_per_level
```

La méthode accepte `available_capital` en argument mais ne l'utilise **jamais** pour le calcul — elle retourne toujours la valeur fixée à l'init. L'argument ne sert qu'à un guard `<= 0`.

**Impact:** Le code est **trompeur**. Un développeur pourrait croire que le capital dynamique est recalculé. De plus, si `available_capital` est 0 (capital épuisé), la méthode retourne `0.0` mais `_can_open_position()` ne le vérifie qu'après le check `max_positions` — c'est correct mais fragile.

**Sévérité:** 🟡 MOYENNE — Principalement un problème de lisibilité/maintenabilité, pas un bug de trading actif.

---

### 🚨 CRITIQUE — Trend: Volume `-1` comme convention non-standard

**Fichier:** `trend.py`, ligne ~128

```python
signal = TradingSignal(
    type=SignalType.SELL,
    symbol=symbol,
    price=price,
    volume=-1,  # CORRECTION: -1 = close all, pas 0
    ...
)
```

`volume=-1` est une **convention ad-hoc** (documentée dans un commentaire). Si le `SignalHandler` ne gère pas correctement cette convention :
- Un volume négatif pourrait être interprété comme un **short**
- Ou rejeté par l'API Kraken

**Sévérité:** 🟡 MOYENNE — Fonctionnel si le SignalHandler le gère, mais c'est une bombe à retardement si le code est modifié.

**Correction:** Utiliser `SignalType.CLOSE` (qui existe !) au lieu de `SignalType.SELL` avec `volume=-1`.

---

### 🟡 MODÉRÉ — P&L: Asymétrie des frais buy/sell

**Fichier:** `instance.py`, `close_position()` lignes ~195-197

```python
buy_fee = position.buy_price * position.volume * 0.0016   # Maker 0.16%
sell_fee = sell_price * position.volume * 0.0026           # Taker 0.26%
```

**Problème:** Le calcul suppose **toujours** maker à l'achat et taker à la vente. En réalité :
- Les ordres **market** (dont les urgences) sont toujours **taker** (0.26%) des deux côtés
- Les ordres **limit** sont **maker** (0.16%) s'ils ne sont pas immédiatement exécutés

La grille utilise des signaux qui **ne précisent pas** le type d'ordre. Si l'exécution est en market (probable pour le bot), les frais d'achat sont sous-estimés de 0.10% (0.16% vs 0.26%).

**Impact sur la rentabilité:**
- Frais réels (market/market): `0.26% + 0.26% = 0.52%`
- Frais calculés (maker/taker): `0.16% + 0.26% = 0.42%`
- **Sous-estimation de 0.10% par trade** → sur 100 trades, ~10% d'écart dans le P&L affiché

**Sévérité:** 🟡 MOYENNE — Le P&L affiché sera optimiste par rapport à la réalité.

---

### 🟢 OK — Kelly Criterion

```python
kelly = (win_rate * b - loss_rate) / b
return max(0.0, min(kelly / 2, 0.25))
```

**Vérification mathématique:** La formule de Kelly est `f* = (p × b − q) / b` où `p` = win rate, `q` = 1−p, `b` = ratio win/loss. ✅ Correct.

Le Half-Kelly (`kelly / 2`) est une pratique standard pour réduire la variance. Le cap à 25% est raisonnable.

**Note:** Kelly n'est **pas utilisé activement** dans les stratégies actuelles. Grid utilise un sizing fixe, Trend utilise `percentage_capital(50%)`. Kelly est disponible mais dormant.

---

### 🟢 OK — Drawdown Calculation

```python
drawdown = (self._peak_capital - self._current_capital) / self._peak_capital
self._max_drawdown = max(self._max_drawdown, drawdown)
```

✅ Formule standard de drawdown depuis le pic. Correctement mise à jour à chaque fermeture de position.

---

### 🟢 OK — Rolling RSI (Wilder's Smoothing)

L'implémentation utilise correctement le lissage de Wilder :
```python
self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period
```

✅ Conforme à la formule standard RSI. La transition SMA → Wilder's après la période d'initialisation est correcte.

---

### 🟢 OK — Rolling EMA

```python
self.multiplier = 2.0 / (period + 1)
self.ema = (price - self.ema) * self.multiplier + self.ema
```

✅ Formule EMA standard. Le facteur multiplicateur `2/(N+1)` est correct.

**Note mineure:** L'initialisation utilise le premier prix comme seed (`self.ema = price`). Les bibliothèques professionnelles utilisent souvent la SMA des N premières valeurs. L'impact est négligeable après ~3×period de données.

---

## 2 — ⚠️ BIAIS DE TRADING IDENTIFIÉS

### ⚠️ BIAIS #1 — Grid: Biais ACHETEUR structurel

**Mécanisme:** `_get_buy_levels()` retourne tous les niveaux sous le prix actuel non occupés. `_get_sell_levels()` ne vend que les positions en profit (au-dessus du seuil).

**Conséquence en marché baissier:**
1. Le prix descend → le bot achète à chaque niveau
2. Le prix continue de descendre → le bot achète encore (tant que `max_positions` non atteint)
3. Le prix remonte partiellement → seules les positions les plus basses sont en profit
4. Les positions hautes restent **bloquées** (en perte latente)

Avec `max_positions=10` et `max_capital_per_level=50€`, le bot peut allouer **500€** dans un marché en chute avant que le stop-loss ne se déclenche (à -10% par position).

**Le stop-loss de -10% par position est la seule protection**, et il déclenche des ventes **à perte**. La grille n'a pas de mécanisme pour refuser d'acheter quand la tendance est clairement baissière.

---

### ⚠️ BIAIS #2 — Grid: Vente systématiquement trop rapide

Le seuil de vente est :
```python
grid_step = self.range_percent / (self.num_levels - 1)  # 7/14 = 0.5%
self._sell_threshold_pct = max(0.5, grid_step * 0.8)    # max(0.5, 0.4) = 0.5%
```

Avec un range de 7% et 15 niveaux, le step est 0.5% et le seuil de vente est **0.5%** au-dessus du prix du niveau.

**Problème:** Après frais (0.42% à 0.52%), un gain de 0.5% brut ne laisse que **~0.0% net** de profit. Le bot vend essentiellement **au break-even** ou à perte légère. Il faudrait un seuil de vente d'au moins **1.0%** pour dégager un profit net après frais.

---

### ⚠️ BIAIS #3 — Trend: 50% du capital en un seul trade

```python
volume = PositionSizing.percentage_capital(available, 50) / price
```

La stratégie Trend investit **50% du capital disponible** sur chaque signal d'achat. C'est extrêmement agressif :
- Un seul faux signal = perte potentielle de 50% × 5% (stop-loss) = **2.5% du capital**
- Combiné avec le lag des EMA (voir biais #4), les faux signaux sont fréquents

**Comparaison:** Les pratiques institutionnelles recommandent 1-2% de risque par trade maximum.

---

### ⚠️ BIAIS #4 — Trend: Lag des EMA non compensé

Les EMA(10) et EMA(30) sont des indicateurs **retardés** par nature. Le crossover (golden/death cross) se produit **après** que le mouvement a déjà commencé.

**En marché crypto volatile:**
- Golden cross confirmé → le prix a déjà monté de 3-5%
- Death cross confirmé → le prix a déjà baissé de 3-5%
- Le bot achète **en retard** et vend **en retard**
- Le stop-loss à -5% peut être touché avant que le death cross ne confirme la sortie

**Le RSI(14) aide peu** car il est lui-même un indicateur retardé. Le filtre surachat/survente est correct en théorie mais ne compense pas le lag fondamental des MA.

---

### ⚠️ BIAIS #5 — Trend: Pas d'adaptation à la volatilité

Le sizing est fixe (50% du capital) quelle que soit la volatilité. En crypto :
- Volatilité basse (range) : 50% est excessif, risque de whipsaw
- Volatilité haute (trend fort) : 50% pourrait être correct mais le stop à -5% est trop serré

L'instance calcule la volatilité (`get_volatility()`) mais **aucune stratégie ne l'utilise** pour ajuster le sizing ou les seuils.

---

### ⚠️ BIAIS #6 — Grid: `best_level = max(buy_levels)` crée un effet d'ancrage

```python
buy_levels = self._get_buy_levels(price)
if buy_levels:
    best_level = max(buy_levels)  # Plus proche du prix actuel
```

Le bot achète toujours au niveau le **plus proche** du prix actuel. En marché descendant rapide :
1. Prix à 48000 → achète niveau 48100
2. Prix descend à 47500 → achète niveau 47600
3. Prix descend à 47000 → achète niveau 47100

Il accumule des positions de plus en plus basses, **sans jamais profiter des niveaux intermédiaires qui pourraient donner un meilleur prix moyen**. Le bot devrait pouvoir acheter à des niveaux plus bas si le momentum est baissier.

---

## 3 — 📊 ANALYSE DE RENTABILITÉ

### 3.1 Break-Even Analysis — Grid Strategy

**Paramètres:**
- Centre: 50,000€ | Range: ±3.5% | Niveaux: 15 | Capital/niveau: 50€
- Frais Kraken: 0.16% (maker) + 0.26% (taker) = **0.42% minimum par trade round-trip**
- Seuil de vente: 0.5% au-dessus du niveau

**Calcul par trade:**
```
Gain brut = 0.5% × 50€ = 0.25€
Frais achat (maker) = 0.16% × 50€ = 0.08€
Frais vente (taker) = 0.26% × 50.25€ = 0.13€
Gain net = 0.25€ - 0.08€ - 0.13€ = +0.04€ par trade
```

**⚠️ Gain net de seulement 0.04€ par trade (0.08% du capital investi).**

Si on utilise des ordres market des deux côtés (plus réaliste):
```
Frais achat (taker) = 0.26% × 50€ = 0.13€
Frais vente (taker) = 0.26% × 50.25€ = 0.13€
Gain net = 0.25€ - 0.13€ - 0.13€ = -0.01€ par trade ← PERTE NETTE
```

**🚨 Avec des ordres market, le seuil de vente actuel (0.5%) est INSUFFISANT. Le bot perd de l'argent sur chaque trade "gagnant".**

### Break-even seuil de vente (ordres taker/taker)

```
Seuil minimum = frais totaux = 0.52%
Seuil avec marge = 0.52% × 1.5 = 0.78% (recommandé)
Seuil confortable = 1.0% (pour absorber le slippage)
```

### 3.2 Impact du Slippage

En crypto, le slippage typique sur Kraken pour des ordres < 100€ est de 0.05-0.15%. Avec le seuil actuel de 0.5%, le slippage mange **10-30%** du gain brut.

### 3.3 Break-Even Analysis — Trend Strategy

**Paramètres:**
- Capital: 1000€ | Sizing: 50% = 500€ par trade
- Stop-loss: -5% | Take-profit: variable (death cross)
- Frais: 0.52% par round-trip (market/market)

**Pour atteindre le break-even:**
```
Perte par trade perdant = 500€ × 5% + frais = 25€ + 2.60€ = 27.60€
Gain moyen nécessaire par trade gagnant pour un win rate de 40% (typique trend following):

win_rate × avg_gain = (1 - win_rate) × avg_loss
0.40 × G = 0.60 × 27.60
G = 41.40€

Gain en % requis = 41.40€ / 500€ = 8.28%
```

**Pour un win rate de 40%, chaque trade gagnant doit capter un mouvement de +8.28% minimum.** Avec des EMA(10/30), le lag typique est de 3-5% sur l'entrée et 3-5% sur la sortie, ce qui laisse un gap capturé d'environ **5-10%** sur un mouvement de 15%. C'est **juste** pour être rentable.

### 3.4 Capital Minimum Réaliste

**Grid Strategy:**
- Min théorique (code): `max_positions × 5€ / 0.90 = 10 × 5€ / 0.90 = 55.56€`
- Min pratique pour rentabilité: Avec 50€/niveau, 10 positions = **500€ minimum**
- Min recommandé (marge de sécurité + drawdown): **1,000€**

**Trend Strategy:**
- Min pour absorber 5 pertes consécutives: `5 × 2.5% = 12.5%` drawdown
- Min pratique: **500€** (sinon les frais fixes mangent les gains)
- Min recommandé: **1,000€**

### 3.5 Rentabilité Théorique Estimée

| Scénario | Grid (mensuel) | Trend (mensuel) |
|----------|----------------|-----------------|
| Marché latéral (±5%) | +1% à +3% | -2% à 0% |
| Marché haussier (+15%) | -1% à +1% (vend trop tôt) | +5% à +10% |
| Marché baissier (-15%) | -5% à -10% (accumule) | -2% à -5% (stop-loss) |
| Flash crash (-30%) | -10% (emergency stop) | -5% (stop-loss fixe) |

**Note:** Ces estimations incluent les frais Kraken mais PAS le slippage. La réalité sera 0.5-1% plus défavorable.

---

## 4 — 🎯 SCÉNARIOS DE RISQUE

### Scénario 1: Marché Latéral (Range-Bound)

**Comportement attendu:** Grid achète bas, vend haut → profit
**Comportement réel:**
- ✅ La grille fonctionne comme prévu
- ⚠️ Avec un seuil de vente de 0.5% et des frais de 0.42-0.52%, le profit net est **quasi nul**
- ⚠️ Si le range est < 7% (ex: 3%), seuls 2-3 niveaux sont activés → sous-utilisation
- ✅ La protection drawdown n'est pas déclenchée
- **Verdict:** Fonctionne mais **marginalement rentable** avec les paramètres actuels

### Scénario 2: Trend Fort Haussier (+20% en une semaine)

**Comportement Grid:**
- 🚨 Le bot vend à +0.5% au-dessus de chaque niveau
- Avec un mouvement de +20%, le bot vend **toutes** ses positions dans les premiers +3.5% (top de la grille)
- Le bot se retrouve **100% cash** sans positions alors que le prix continue de monter
- Aucun mécanisme de re-centrage automatique de la grille
- **Perte d'opportunité massive**

**Comportement Trend:**
- ✅ Golden cross détecté (avec lag de 3-5%)
- ✅ Achat à 50% du capital
- ⚠️ RSI pourrait bloquer l'entrée si > 70 (surachat pendant un bull run)
- ✅ Pas de take-profit prématuré (vente uniquement sur death cross)
- **Verdict:** Capture une bonne partie du mouvement, mais entrée retardée

### Scénario 3: Trend Fort Baissier (-20% en une semaine)

**Comportement Grid:**
- 🚨🚨 **SCÉNARIO LE PLUS DANGEREUX**
- Le bot achète à **chaque niveau** en descendant (10 positions max)
- Investissement total: 10 × 50€ = 500€ (ou `_runtime_capital_per_level × 10`)
- Stop-loss par position: -10% → perte max par position = 50€ × 10% = 5€
- **Mais:** Les stop-loss se déclenchent **individuellement**, pas en cascade
- Si le prix descend de 20%, les positions hautes touchent -10% bien avant les basses
- Avec `_emergency_close_price` à `center × (1 - 7% × 2)` = `center × 0.86` (-14%), l'emergency mode se déclenche et ferme **tout** au market
- **Perte estimée:** 7-14% du capital grid + frais d'urgence

**Comportement Trend:**
- ✅ Stop-loss à -5% protège le capital
- ⚠️ Si déjà en position: perte = 50% × 5% = 2.5% du capital
- ✅ Death cross empêche de racheter pendant la descente
- **Verdict:** Bien protégé

### Scénario 4: Flash Crash (-30% en 1 heure, rebond +25%)

**Comportement Grid:**
- 🚨 Emergency mode activé rapidement (seuil -14%)
- Toutes les positions vendues **au pire moment** (market sell en bas du crash)
- Quand le prix rebondit, le bot est en mode urgence → **aucun achat**
- `_emergency_mode` est un bool permanent → **le bot ne reprend JAMAIS** sans reset manuel
- **Perte maximale** et **zéro récupération**

**Comportement Trend:**
- Stop-loss déclenché à -5% → vente partielle
- Pas de rachat pendant le rebond (death cross confirmé)
- **Perte limitée mais pas de récupération**

### Scénario 5: Pump & Dump (+40% puis -45% en 2h)

**Comportement Grid:**
- Phase pump: vend toutes les positions rapidement (+0.5% chacune) → petit profit
- Se retrouve sans positions en haut
- Phase dump: la grille tente d'acheter en descendant mais les niveaux sont trop hauts
- Emergency mode si le dump dépasse le seuil
- **Verdict:** Le profit de la phase pump ne compense pas le risque de la phase dump

**Comportement Trend:**
- Golden cross pendant le pump → achat (retardé)
- RSI > 80 → vente en take-profit (bon timing SI le RSI monte assez vite)
- ⚠️ Si le pump est trop rapide, la vente RSI > 80 peut ne pas se déclencher à temps
- Death cross pendant le dump → vente (retardée de 3-5%)
- **Perte potentielle de 5-10%** si le stop-loss ne couvre pas le dump rapide

---

## 5 — 💡 SUGGESTIONS D'AMÉLIORATION

### 🔴 PRIORITÉ HAUTE

#### 1. Corriger `calculate_grid_levels()` — Utiliser des niveaux géométriques
```python
def calculate_grid_levels(center_price, range_percent, num_levels):
    if num_levels < 2:
        return [center_price]
    ratio = (1 + range_percent / 100) ** (1 / (num_levels - 1))
    half = (num_levels - 1) / 2
    return sorted([center_price * ratio ** (i - half) for i in range(num_levels)])
```

#### 2. Corriger le capital: utiliser `get_available_capital()` au lieu de `get_current_capital()`
Dans `grid.py` → `on_price()`:
```python
available_capital = self.instance.get_available_capital()  # PAS get_current_capital()
```

#### 3. Augmenter le seuil de vente minimum à 1.0%
```python
self._sell_threshold_pct = max(1.0, grid_step * 1.2)  # Couvre frais + marge
```
Cela garantit un profit net d'au moins **0.48%** par trade (1.0% - 0.52% frais).

#### 4. Ajouter un auto-reset de `_emergency_mode`
```python
# Dans on_price(), si le prix revient dans la grille:
if self._emergency_mode and price > self.grid_levels[len(self.grid_levels) // 3]:
    self._emergency_mode = False
    logger.info("✅ Emergency mode désactivé - prix revenu dans la grille")
```

### 🟡 PRIORITÉ MOYENNE

#### 5. Ajouter un filtre de tendance à la Grid
Avant d'acheter, vérifier que le prix n'est pas en chute libre:
```python
# Calculer momentum court terme
if len(self._price_history) >= 10:
    recent = list(self._price_history)[-10:]
    momentum = (recent[-1] - recent[0]) / recent[0] * 100
    if momentum < -2.0:  # Chute de >2% sur 10 ticks
        return  # Ne pas acheter en descente rapide
```

#### 6. Réduire le sizing Trend de 50% à 20-30%
```python
volume = PositionSizing.percentage_capital(available, 25) / price  # 25% max
```
Ou mieux, utiliser le Kelly Criterion déjà implémenté:
```python
if self.instance._win_count + self.instance._loss_count >= 20:
    total = self.instance._win_count + self.instance._loss_count
    win_rate = self.instance._win_count / total
    kelly_pct = PositionSizing.kelly_criterion(win_rate, avg_win, avg_loss) * 100
    volume = PositionSizing.percentage_capital(available, kelly_pct) / price
```

#### 7. Adapter le stop-loss Trend à la volatilité
```python
volatility = self.instance.get_volatility()
dynamic_sl = max(0.03, min(0.08, volatility * 2))  # SL = 2× volatilité, entre 3% et 8%
if self._entry_price and current_price < self._entry_price * (1 - dynamic_sl):
    return True  # Sell
```

#### 8. Utiliser `SignalType.CLOSE` au lieu de `volume=-1`
```python
signal = TradingSignal(
    type=SignalType.CLOSE,  # Pas SELL avec volume=-1
    symbol=symbol,
    price=price,
    volume=0,  # Ignoré pour CLOSE
    ...
)
```

### 🟢 PRIORITÉ BASSE

#### 9. Ajouter un re-centrage automatique de la grille
Quand le prix sort durablement de la grille (>1h hors range), re-centrer automatiquement:
```python
if all positions closed and price outside grid for > 1 hour:
    self.center_price = current_price
    self._init_grid()  # Recalcule les niveaux
```

#### 10. Différencier les frais maker/taker dans le P&L
Passer le type d'ordre (limit/market) au calcul de P&L pour des frais précis:
```python
def close_position(self, position_id, sell_price, order_type='market'):
    fee_rate = 0.0016 if order_type == 'limit' else 0.0026
```

#### 11. Implémenter un trailing stop-loss pour Trend
Au lieu d'un stop fixe à -5%, utiliser un trailing stop qui remonte avec le prix:
```python
self._highest_since_entry = max(self._highest_since_entry, current_price)
trailing_sl = self._highest_since_entry * 0.95
if current_price < trailing_sl:
    # Sell — protège les gains
```

---

## 📋 RÉSUMÉ EXÉCUTIF

| Catégorie | Score | Commentaire |
|-----------|-------|-------------|
| **Correction mathématique** | 6/10 | Grille non-géométrique, confusion capital total/disponible |
| **Gestion des risques** | 7/10 | Stop-loss présents, emergency mode, mais mode non-réversible |
| **Rentabilité Grid** | 3/10 | Seuil de vente trop bas → quasi break-even après frais |
| **Rentabilité Trend** | 5/10 | Viable en forte tendance, trop agressif en sizing |
| **Résilience aux crashes** | 5/10 | Emergency mode OK mais pas de recovery automatique |
| **Qualité du code** | 8/10 | Thread-safety soigné, bonne documentation, conventions claires |

### 🎯 TOP 3 des corrections à faire immédiatement:

1. **🔴 Augmenter `_sell_threshold_pct` à ≥ 1.0%** — Sans cela, le bot Grid perd de l'argent sur chaque trade "gagnant"
2. **🔴 Utiliser `get_available_capital()`** au lieu de `get_current_capital()` dans la Grid — Évite les achats quand le capital est épuisé
3. **🟡 Réduire le sizing Trend de 50% à 20-25%** — Réduit l'exposition catastrophique sur faux signaux

---

*Fin du rapport d'audit — 2026-03-11*