# Review Opus 4.6 — Adaptive Grid V3

**Date:** 2026-04-07  
**Reviewer:** Claude Opus 4.6  
**Fichiers:** 5 fichiers, 1876 lignes  
**Scope:** Architecture, performance, thread-safety, rétro-compatibilité

---

## Résumé

L'architecture V3 est solide et bien pensée : séparation hot-path/cold-path rigoureuse, pattern Strategy/Registry proprement implémenté, et rétro-compatibilité préservée à 100% grâce au fallback transparent vers le comportement legacy. Les composants sont faiblement couplés (bon pour la testabilité). Quelques problèmes de race conditions et un singleton non thread-safe méritent attention avant la mise en production.

---

## Points forts

- **Hot-path O(1) respecté partout** : `get_current_range()` retourne un float caché, `should_recenter()` fait uniquement des comparaisons numériques, `PairProfileRegistry.get()` est un dict lookup. Aucune allocation sur le chemin critique.

- **Séparation hot/cold exemplaire** : Les calculs coûteux (HV, recomputation de la grille, ATR) sont explicitement relégués au cold path avec throttle (`_cold_path_counter`, `_update_interval_s`). Le hot path (`on_price`) ne fait que des O(1) appends et des checks booléens.

- **Rétro-compatibilité parfaite** : Sans `PairProfile`, le comportement est 100% identique à V2 (7% range, 15 levels, brutal DGT). Les lazy imports évitent les erreurs si les modules V3 ne sont pas déployés. Le pattern fallback est irréprochable.

- **`PairProfile` frozen + slots** : Immutabilité garantie par `@dataclass(frozen=True, slots=True)`. Pas de mutation accidentelle possible. Excellent pour la sûreté en concurrent.

- **Progressive SmartRecentering** : Le passage de "close all + snap" à "shift 25-75% + close seulement les OOB" est une amélioration majeure qui réduira significativement le P&L whiplash.

- **Introspection exhaustive** : Chaque composant expose un `get_status()` riche. Excellent pour le debugging et le dashboard.

- **Calcul HV sans dépendance NumPy** : Le calcul de volatilité historique est fait en pur Python avec une boucle simple — pas de dépendance lourde, performance acceptable sur le cold path.

- **DynamicGridAllocator stateless** : Méthodes `@staticmethod`, fonctions pures, pas d'état. Testabilité maximale.

---

## Problèmes

### CRITICAL

- **[adaptive_grid_config.py:283-286] — Singleton `get_default_registry()` non thread-safe (race condition)**  
  Le pattern lazy-init du singleton utilise un simple `global _registry` sans lock. Si deux coroutines appellent `get_default_registry()` simultanément lors du premier appel, deux instances peuvent être créées. L'une sera perdue (garbage collected) mais la seconde pourrait avoir un état différent si `register()` a été appelé entre-temps.  
  **Fix:** Utiliser un `threading.Lock` ou mieux, initialiser le singleton au module level (eager init) :
  ```python
  _registry = PairProfileRegistry()  # module-level eager init
  def get_default_registry() -> PairProfileRegistry:
      return _registry
  ```

- **[smart_recentering.py:127-129] — `should_recenter()` mute l'état sans lock**  
  `should_recenter()` est documenté comme "hot-path O(1)" mais il modifie `_recent_prices`, `_recenters_today`, et `_today_date` sans protection du `_lock`. Si `should_recenter()` est appelé depuis le hot path et `async_recenter()` depuis le cold path en parallèle, `_recenters_today` peut être incohérent.  
  **Fix:** Soit rendre `should_recenter()` readonly (ne pas y tracker les prix), soit utiliser le lock. Recommandation : séparer l'ingestion de prix (`on_price_tick()`) de la query (`should_recenter()`).

### HIGH

- **[smart_recentering.py:155-158] — `_recent_prices` list slicing O(N) sur hot path**  
  ```python
  self._recent_prices.append(price)
  if len(self._recent_prices) > self.velocity_window:
      self._recent_prices = self._recent_prices[-self.velocity_window:]
  ```
  Le slicing crée une nouvelle liste à chaque dépassement — O(N) + allocation. Devrait être un `deque(maxlen=velocity_window)` comme dans `range_calculator.py`.  
  **Fix:**
  ```python
  self._recent_prices: deque = deque(maxlen=velocity_window)
  ```

- **[grid_async.py:~340-360] — `_maybe_update_adaptive()` recalcule la grille sans lock**  
  La recomputation modifie `self.range_percent`, `self.num_levels`, `self.grid_levels`, `self._sell_threshold_pct`, et `self._emergency_close_price` de manière non-atomique. Si `on_price()` est ré-entré (via un callback de signal qui trigger un nouveau tick ?), les données pourraient être dans un état intermédiaire.  
  En asyncio single-threaded, c'est normalement safe car `on_price()` est synchrone et non-interruptible. Mais si `emit_signal()` trigger des awaits en aval qui relancent le loop, il y a un risque.  
  **Risque:** MOYEN en asyncio pur, ÉLEVÉ si mélangé avec du threading.  
  **Fix:** Documenter explicitement que `on_price()` DOIT être appelé depuis la même coroutine, ou ajouter un guard `_updating = True`.

- **[grid_async.py:~260] — `_find_nearest_level()` est O(N) — appelé sur le hot path**  
  Scan linéaire de tous les niveaux. Avec max 30 niveaux c'est acceptable, mais la docstring de la V3 promet O(1) sur le hot path.  
  **Fix:** Utiliser `bisect.bisect_left()` pour O(log N), ou pré-calculer un dict `{level: idx}` si les niveaux sont fixes entre les updates.

- **[adaptive_grid_config.py:236-240] — `PairProfileRegistry.register()` mute le dict après construction**  
  La docstring et le commentaire disent "immutable after init" / "read-only afterwards", mais `register()` permet de muter `_profiles` à tout moment. Si le hot path lit `_profiles` pendant qu'un cold path appelle `register()`, le dict pourrait être dans un état inconsistant (en CPython c'est safe grâce au GIL pour les dict ops atomiques, mais c'est un contrat implicite fragile).  
  **Fix:** Soit supprimer `register()` et forcer la construction à l'init, soit documenter explicitement le contrat de thread-safety.

### MEDIUM

- **[range_calculator.py:148-165] — `_compute_hv()` O(N) avec N=10080 (7 jours)**  
  Le cold path itère sur ~10K éléments pour le HV 7d. C'est ~0.5ms en Python pur. Acceptable à 60s d'intervalle, mais pourrait devenir un problème si l'intervalle est réduit.  
  **Optimisation possible:** Calculer incrémentalement (Welford's online algorithm) au lieu de tout re-scanner.

- **[range_calculator.py:155] — Pas de copie défensive pour l'itération sur deque**  
  `_compute_hv()` itère directement sur la deque qui peut être modifiée par `on_price()` depuis le même thread (asyncio). En pratique safe en asyncio single-threaded, mais fragile.

- **[smart_recentering.py:83] — `_recenter_history` croît sans limite**  
  La liste `_recenter_history` n'est jamais tronquée. Avec max 4 recenters/jour, ça prendra des mois pour devenir un problème, mais c'est un memory leak lent.  
  **Fix:** `deque(maxlen=100)` ou trim périodique.

- **[multi_grid_orchestrator.py:99-100] — `object.__setattr__` sur un dataclass non-frozen**  
  `SubGridConfig` n'est pas frozen, donc `sg.capital_share = ...` suffirait. L'utilisation de `object.__setattr__` est superflue et suggère que le dev pensait que `SubGridConfig` était frozen (ce qui n'est pas le cas). Risque de confusion.  
  **Fix:** Soit rendre `SubGridConfig` frozen, soit utiliser l'affectation directe.

- **[multi_grid_orchestrator.py:114-120] — `on_price()` n'a pas de fast-path pour les erreurs**  
  Le `try/except` dans la boucle `on_price()` catch toutes les exceptions silencieusement et continue. Un bug dans un sub-grid pourrait passer inaperçu pendant des heures.  
  **Fix:** Ajouter un compteur d'erreurs et/ou une alerte après N erreurs consécutives.

- **[grid_async.py] — Duplication de `_DEFAULT_PROFILES` (BTC EUR/USD, ETH EUR/USD)**  
  Les profils BTC EUR et BTC USD sont identiques, idem pour ETH. Pourrait être factorisé avec un helper `_make_profile(symbol, **overrides)`.

- **[grid_async.py:~380-395] — SmartRecenter: `positions_to_close` indices vs `open_levels` keys**  
  `result.positions_to_close` contient des indices de niveaux retournés par `compute_recenter()`. Le code itère correctement mais si la grille a été recalculée entre le `should_recenter()` et le `compute_recenter()`, les indices pourraient ne plus correspondre. Window très petite en asyncio, mais théoriquement possible.

- **[grid_async.py] — Pas de tests unitaires visibles dans le scope de la review**  
  L'architecture est très testable (fonctions pures, composants découplés), mais aucun test n'a été fourni pour review. Les edge cases (capital=0, atr_pct=NaN, deque vide) mériteraient une couverture.

---

## Recommandations architecturales

1. **Adopter le pattern "Immutable Config + Mutable State"** plus strictement : `PairProfile` est déjà immutable (bien), mais le `PairProfileRegistry` devrait l'être aussi. Séparer en `PairProfileRegistry` (immutable, init-only) et `RuntimeProfileStore` (mutable, locked).

2. **Considérer un EventBus** pour découpler `on_price` → adaptive update → grid rebuild. Actuellement tout est dans `on_price()` via `_maybe_update_adaptive()`. Un bus permettrait de tester chaque étape indépendamment.

3. **Ajouter des métriques Prometheus/StatsD** sur le hot path : latence `on_price()`, nombre de recenters, range actuel, etc. Les `get_status()` sont bien mais pas suffisants pour le monitoring real-time.

4. **Typing strict** : Les `Any` dans `grid_async.py` (pour `instance`, `_dgt`, etc.) réduisent la sûreté du type checking. Introduire des `Protocol` pour définir les interfaces attendues.

---

## Matrice de compatibilité

| Scénario | Comportement | ✅/❌ |
|----------|-------------|-------|
| V2 config, pas de PairProfile | Legacy 7%/15lvl/brutal DGT | ✅ Identique |
| V2 config + modules V3 pas installés | Fallback gracieux (lazy import) | ✅ Safe |
| V3 config + PairProfile BTC | Adaptive range + SmartRecenter | ✅ OK |
| V3 config + pair inconnue | Fallback profile (7%/15lvl) | ✅ OK |
| Multi-grid activé | Short+Long grids orchestrés | ✅ OK |
| center_price=None (auto-init) | Init au premier prix reçu | ✅ OK |

---

## Statistiques

| Métrique | Valeur |
|----------|--------|
| Lignes totales | 1876 |
| Complexité hot-path | O(1) sauf `_find_nearest_level` O(N) |
| Complexité cold-path | O(N) max N=10080 |
| Locks asyncio | 1 (`SmartRecentering._lock`) |
| Race conditions identifiées | 3 (1 CRITICAL, 2 HIGH) |
| Memory leaks potentiels | 1 (`_recenter_history`) |

---

## Verdict

**NEEDS_FIX**

L'architecture est excellente — bien layered, bonne séparation des concerns, rétro-compatible. Mais les 2 issues CRITICAL (singleton race + mutation sans lock dans `should_recenter`) doivent être corrigées avant merge. Les issues HIGH (`deque` au lieu de list slicing, `_find_nearest_level` O(N)) sont des quick wins qui devraient être adressées dans la même PR.

Estimation de fix : **2-3 heures** pour les CRITICAL + HIGH. Le reste peut aller dans un ticket de suivi.
