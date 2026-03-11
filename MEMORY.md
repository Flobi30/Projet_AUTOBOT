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
- **System**: Ready for paper trading (all critical/major issues resolved)
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
1. Paper trading with small capital (100€)
2. 48h dry run monitoring
3. Decide on multi-market approach (keep current or revert to conservative)
4. Production deployment if paper trading successful

## Important Notes
- User is Flo (AUTOBOT project owner)
- First worked with Devin AI and Claude before this implementation
- Used Gemini + Opus dual review process for validation
- All security reviews passed, architecture solid
- Only remaining concern: market selection philosophy disagreement
