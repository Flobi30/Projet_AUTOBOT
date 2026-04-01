# MEMORY.md - AUTOBOT V2 Project Memory

## Project Overview
AUTOBOT V2 is a crypto/forex/commodity algorithmic trading bot for Flo.
Multi-phase development to make it production-ready.

## Critical Achievements (March 11, 2026)

### Phases Completed
1. ✅ Phase 1: Real Kraken API execution (OrderExecutor)
2. ✅ Phase 2: Native stop-loss management (StopLossManager)
3. ✅ Phase 3: State reconciliation (ReconciliationManager)
4. ✅ Phase 4: Thread-safety and WebSocket robustness
5. ✅ Phase 5: Optimizations (logging, health check, tests, backup)
6. ⚠️ Phase 6: Multi-market auto-selection (implemented but CONTROVERSIAL)

### Phase 1 Performance Modules (April 1, 2026) - ✅ COMPLETE
**Workflow multi-agents mis en place**: Kimi (architecte) → Claude Code (coding) → Opus/Gemini (reviews)

| Module | Status | Tests | Reviews |
|--------|--------|-------|---------|
| ATR Filter | 🟡 Coded | 48/48 | Pending corrections |
| Kelly Criterion | ✅ Complete | 47/47 | ✅ Opus + Gemini OK |
| Regime Detector | ✅ Complete | 68/68 | ✅ Opus + Gemini OK |
| Funding Rates | ✅ Complete | 99/99 | ✅ Opus + Gemini OK |
| Open Interest | ✅ Complete | 99/99 | ✅ Opus + Gemini OK |

**Key technical decisions**:
- All modules: O(1) complexity, RLock thread-safety, zero external dependencies
- Kelly: Half-Kelly (f*/2) with 25% max position cap
- Regime: ADX-based with crisis detection (ATR > baseline × 3)
- Funding: Cooldown mechanism (3 consecutive OK updates to exit pause)

### Phase 8 Shadow Trading (April 1, 2026) - ✅ COMPLETE
| Module | Status | Tests | Reviews |
|--------|--------|-------|---------|
| ShadowTradingManager | ✅ Complete | 35/35 | ✅ Opus + Gemini OK |

**Features**:
- Paper trading instances en parallèle du live
- Promotion live: PF ≥ 1.5 + 30 trades + durée validation (14/21/28j)
- Cap transfert: 25% max capital shadow
- Corrections: time.monotonic(), PF recalculé interne, logs hors lock

### Phase 9 Dashboard Enrichi (April 1, 2026) - ✅ COMPLETE
| Module | Status | Reviews |
|--------|--------|---------|
| Dashboard API | ✅ Complete | ✅ Opus + Gemini OK |

**Nouveaux endpoints**:
- `/api/performance` : PF global et par instance (Sharpe, win rate)
- `/api/drawdown` : Max drawdown et courant
- `/api/shadow-status` : État shadow trading
- `/api/phase1-modules` : Statut modules performance
- `/api/strategies-dormantes` : Mean Reversion, Arbitrage status

**Compatible** avec frontend React existant (/dashboard/src/)

### Critical Fixes Made
- Fixed major wiring issue: OrderExecutor, StopLossManager, ReconciliationManager now properly connected
- Fixed WebSocket crash on list data (isinstance check)
- Fixed Grid capital calculation (get_available_capital vs get_current_capital)
- Fixed allocated capital drift (recalculate_allocated_capital)
- Fixed empty ValidatorEngine (create_default_validator_engine)
- Fixed race conditions (multiple thread-safety fixes)
- Fixed reconciliation stubs (all 6 TODO methods implemented)

### Expert Reviews
- **Gemini**: Approved for testing after fixes. Warns against "best market" auto-selection.
- **Opus**: SAFE_FOR_TESTING after fixes. Recommends "regime-based exclusion" NOT "winner-take-all" selection.

## Current Status
- **System**: Core ready for paper trading (all critical/major issues resolved)
- **Phase 1 Progress**: 4/5 performance modules completed (ATR corrections pending, Open Interest remaining)
- **Controversy**: Multi-market auto-selection implemented but BOTH Gemini and Opus recommend against "best market" approach
- **Recommendation**: Consider reverting to conservative approach (same-market duplication) per expert advice

## Key Decisions
- Grid threshold: 1.5% minimum (covers Kraken fees ~1.04%)
- Trend position sizing: 20% capital per trade
- Max 2 instances per market
- Circuit breaker: 10 consecutive API errors
- SQLite backup: Daily automatic
- Log rotation: 10MB max, 5 backups

## Next Steps
### Phase 1 Completion (Immediate)
1. Complete Open Interest module
2. Apply ATR Filter corrections from reviews
3. Final review pass on all 5 modules
4. Integration testing with Grid strategy

### Phase 2 Preparation
5. Paper trading with small capital (100€)
6. 48h dry run monitoring
7. Decide on multi-market approach (keep current or revert to conservative)
8. Production deployment if paper trading successful

## Important Notes
- User is Flo (AUTOBOT project owner)
- First worked with Devin AI and Claude before this implementation
- Used Gemini + Opus dual review process for validation
- All security reviews passed, architecture solid
- Only remaining concern: market selection philosophy disagreement
