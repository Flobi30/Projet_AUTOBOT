    def attach_speculative_cache(self, cache: SpeculativeOrderCache) -> None:
        self._spec_cache = cache
        self._precompute_speculative_templates()

    def _precompute_speculative_templates(self) -> None:
        if self._spec_cache is None:
            return
        symbol = self.instance.config.symbol
        self._spec_cache.invalidate_symbol(symbol)
        self._spec_cache.precompute_grid_levels(
            symbol=symbol,
            grid_levels=self.grid_levels,
            capital_per_level=self._runtime_capital_per_level,
        )
        logger.debug(
            "GridAsync P6: %d templates BUY pre-calcules pour %s",
            len(self.grid_levels), symbol,
        )

    def _find_nearest_level(self, price: float) -> int:
        if not self.grid_levels:
            return -1
        nearest_idx = 0
        min_dist = abs(price - self.grid_levels[0])
        for i, level in enumerate(self.grid_levels):
            d = abs(price - level)
            if d < min_dist:
                min_dist = d
                nearest_idx = i
        return nearest_idx

    def _get_buy_levels(self, current_price: float) -> List[int]:
        nearest = self._find_nearest_level(current_price)
        if nearest < 0:
            return []
        return [i for i in range(nearest) if i not in self.open_levels]

    def _get_sell_levels(self, current_price: float) -> List[int]:
        sells = []
        for idx in self.open_levels:
            if current_price > self.grid_levels[idx] * (1 + self._sell_threshold_pct / 100):
                sells.append(idx)
        return sells

    def _can_open_position(self, available_capital: float) -> bool:
        if len(self.open_levels) >= self.max_positions:
            return False
        cpl = self._runtime_capital_per_level
        return cpl > 0 and available_capital >= cpl

    def _check_drawdown(self, price: float) -> Optional[int]:
        for idx, pos in self.open_levels.items():
            dd = (pos["entry_price"] - price) / pos["entry_price"] * 100
            if dd >= self._max_drawdown_pct:
                return idx
        return None

    def _is_grid_invalidated(self, price: float) -> bool:
        return price < self._emergency_close_price

    # ------------------------------------------------------------------
    # on_price — CPU-bound, no I/O
    # ------------------------------------------------------------------

    def on_price(self, price: float) -> None:
        if not self._initialized or not math.isfinite(price) or price <= 0:
            return

        # V3: Feed price to range calculator (O(1) deque append)
        if self._range_calculator is not None:
            self._range_calculator.on_price(price)

        # Dynamic grid initialization on first price received
        if not self._grid_initialized:
            if self.center_price is None:
                self.center_price = price
                logger.info(f"Grid initialisee au prix: {price:.2f}")
            self._init_grid()
            self._grid_initialized = True

            if self._dgt is None and self.config.get("enable_dgt", True):
                self._init_recentering()

            self._emergency_close_price = self.center_price * (
                1 - self.range_percent * self._grid_invalidation_factor / 100
            )

            mode_str = "ADAPTIVE" if self._adaptive_mode else "FIXED"
            logger.info(
                f"GridAsync [{mode_str}]: {self.num_levels} niveaux, "
                f"+/-{self.range_percent:.1f}% sur {self.center_price:.0f}"
            )

        # Stale data check
        if hasattr(self.instance, "orchestrator") and self.instance.orchestrator:
            ws = self.instance.orchestrator.ws_client
            if hasattr(ws, "is_data_fresh") and not ws.is_data_fresh():
                return

        available_capital = self.instance.get_available_capital()
        self._price_history.append(price)
        symbol = self.instance.config.symbol

        # V3: Cold-path adaptive update (every N ticks)
        self._maybe_update_adaptive(price)

        # DGT — trailing anchor
        if self._dgt and not self._emergency_mode:
            self._dgt.check_trailing_anchor(price)

        # DGT — recenter check
        if self._dgt and not self._emergency_mode:
            adx: Optional[float] = None
            if self._regime_detector and hasattr(self._regime_detector, "get_adx"):
                adx = self._regime_detector.get_adx()

            if self._dgt.should_recenter(price, adx=adx):
                # V3 SmartRecentering: progressive shift, selective position close
                if self._adaptive_mode and hasattr(self._dgt, "compute_recenter"):
                    result = self._dgt.compute_recenter(
                        price, self.open_levels, self.grid_levels,
                    )
                    if result.should_recenter:
                        # Close only positions marked for closure
                        positions_closed = set()
                        for i, idx in enumerate(result.positions_to_close):
                            pos = self.open_levels.get(idx)
                            if pos:
                                sig = TradingSignal(
                                    type=SignalType.SELL,
                                    symbol=symbol, price=price,
                                    volume=pos["volume"],
                                    reason=f"SmartRecenter: closing OOB level {idx}",
                                    timestamp=datetime.now(timezone.utc),
                                    metadata={
                                        "level_index": idx,
                                        "smart_recenter": True,
                                        "strategy": "grid",
                                    },
                                )
                                self.emit_signal(sig, bypass_cooldown=(i > 0))
                                positions_closed.add(idx)

                        self.center_price = result.new_center
                        self.grid_levels = result.new_grid_levels
                        for idx in positions_closed:
                            self.open_levels.pop(idx, None)
                        self._emergency_close_price = self.center_price * (
                            1 - self.range_percent * self._grid_invalidation_factor / 100
                        )
                        if self._spec_cache is not None:
                            self._precompute_speculative_templates()
                        return
                else:
                    # Legacy DGT: close all positions, snap to price
                    for i, (idx, pos) in enumerate(list(self.open_levels.items())):
                        sig = TradingSignal(
                            type=SignalType.SELL,
                            symbol=symbol, price=price,
                            volume=pos["volume"],
                            reason=f"DGT: recentering — closing level {idx}",
                            timestamp=datetime.now(timezone.utc),
                            metadata={"level_index": idx, "dgt_recenter": True, "strategy": "grid"},
                        )
                        self.emit_signal(sig, bypass_cooldown=(i > 0))

                    result = self._dgt.recenter(price)
                    self.center_price = result.new_center
                    self.grid_levels = result.new_grid_levels
                    self.open_levels.clear()
                    self._emergency_close_price = self.center_price * (
                        1 - self.range_percent * self._grid_invalidation_factor / 100
                    )
                    if self._spec_cache is not None:
                        self._precompute_speculative_templates()
                    return

        # Emergency mode
        if not self._emergency_mode and self._is_grid_invalidated(price):
            self._emergency_mode = True
            logger.error(f"GRID INVALIDATED: {price:.0f} < {self._emergency_close_price:.0f}")

        if self._emergency_mode:
            for i, (idx, pos) in enumerate(list(self.open_levels.items())):
                sig = TradingSignal(
                    type=SignalType.SELL, symbol=symbol, price=price,
                    volume=pos["volume"],
                    reason=f"EMERGENCY: Grid invalidated - level {idx}",
                    timestamp=datetime.now(timezone.utc),
                    metadata={"level_index": idx, "emergency": True, "strategy": "grid"},
                )
                self.emit_signal(sig, bypass_cooldown=(i > 0))
            return

        # Drawdown check
        emergency_level = self._check_drawdown(price)
        if emergency_level is not None:
            pos = self.open_levels.get(emergency_level)
            if pos:
                sig = TradingSignal(
                    type=SignalType.SELL, symbol=symbol, price=price,
                    volume=pos["volume"],
                    reason=f"STOP-LOSS: Drawdown {self._max_drawdown_pct}% atteint",
                    timestamp=datetime.now(timezone.utc),
                    metadata={"level_index": emergency_level, "stop_loss": True, "strategy": "grid"},
                )
                self.emit_signal(sig)

        # Sells
        sell_levels = self._get_sell_levels(price)
        sell_data = [(idx, self.open_levels[idx], self.grid_levels[idx]) for idx in sell_levels if idx in self.open_levels]
        for i, (idx, pos, lp) in enumerate(sell_data):
            pct = (price - lp) / lp * 100
            sig = TradingSignal(
                type=SignalType.SELL, symbol=symbol, price=price,
                volume=pos["volume"],
                reason=f"Grid level {idx} profit: +{pct:.2f}%",
                timestamp=datetime.now(timezone.utc),
                metadata={"level_index": idx, "level_price": lp, "entry_price": pos["entry_price"], "strategy": "grid"},
            )
            self.emit_signal(sig, bypass_cooldown=(i > 0))

        # Module checks
        if self._regime_detector and not self._regime_detector.should_trade_grid():
            return
        if self._oi_monitor and self._oi_monitor.is_squeeze_risk():
            return

        # Buys
        if self._can_open_position(available_capital):
            buy_levels = self._get_buy_levels(price)
            if buy_levels:
                best = max(buy_levels)
                cpl = self._runtime_capital_per_level
                if cpl > 0:
                    volume = cpl / price
                    sig = TradingSignal(
                        type=SignalType.BUY, symbol=symbol, price=price,
                        volume=volume,
                        reason=f"Grid buy level {best} @ {self.grid_levels[best]:.0f}",
                        timestamp=datetime.now(timezone.utc),
                        metadata={"level_index": best, "level_price": self.grid_levels[best], "strategy": "grid"},
                    )
                    self.emit_signal(sig)

    def on_position_opened(self, position: Any) -> None:
        if not hasattr(position, "buy_price"):
            return
        idx = self._find_nearest_level(position.buy_price)
        if idx >= 0:
            self.open_levels[idx] = {
                "entry_price": position.buy_price,
                "volume": position.volume,
                "opened_at": datetime.now(timezone.utc),
            }
            if self._spec_cache is not None:
                symbol = self.instance.config.symbol
                self._spec_cache.store_sell_template(
                    symbol=symbol,
                    level_index=idx,
                    level_price=self.grid_levels[idx] if idx < len(self.grid_levels) else position.buy_price,
                    volume=position.volume,
                )

    def on_position_closed(self, position: Any, profit: float) -> None:
        if not hasattr(position, "buy_price"):
            return
        idx = self._find_nearest_level(position.buy_price)
        self.open_levels.pop(idx, None)
        if self._spec_cache is not None:
            symbol = self.instance.config.symbol
            self._spec_cache.invalidate(symbol, "sell", idx)

    def reset(self) -> None:
        self.open_levels.clear()
        self._price_history.clear()
        self._emergency_mode = False
        self._cold_path_counter = 0
        super().reset()

    # ------------------------------------------------------------------
    # V3: Status with adaptive info
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        status.update({
            "adaptive_mode": self._adaptive_mode,
            "range_percent": self.range_percent,
            "num_levels": self.num_levels,
            "center_price": self.center_price,
            "open_levels_count": len(self.open_levels),
            "capital_per_level": self._runtime_capital_per_level,
            "grid_initialized": self._grid_initialized,
            "emergency_mode": self._emergency_mode,
        })
        if self._range_calculator:
            status["range_calculator"] = self._range_calculator.get_status()
        if self._dgt and hasattr(self._dgt, "get_status"):
            status["recentering"] = self._dgt.get_status()
        if self._pair_profile:
            status["pair_profile"] = self._pair_profile.symbol
        return status
