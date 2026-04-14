"""
Tests for PairProfileRegistry and DynamicGridAllocator.
"""

import pytest
from autobot.v2.strategies.adaptive_grid_config import (
    PairProfile,
    PairProfileRegistry,
    DynamicGridAllocator,
    get_default_registry,
    _FALLBACK_PROFILE,
)


# ====================================================================
# PairProfile
# ====================================================================

class TestPairProfile:
    def test_default_values(self):
        p = PairProfile(symbol="TEST")
        assert p.symbol == "TEST"
        assert p.base_range_pct == 7.0
        assert p.min_range_pct == 2.0
        assert p.max_range_pct == 15.0
        assert p.base_num_levels == 15
        assert p.min_levels == 5
        assert p.max_levels == 30
        assert p.max_capital_per_level == 50.0
        assert p.capital_weight == 1.0
        assert p.atr_multiplier == 2.5
        assert p.enable_multi_grid is False
        assert p.tags == ()

    def test_immutable(self):
        p = PairProfile(symbol="BTC")
        with pytest.raises(AttributeError):
            p.symbol = "ETH"  # type: ignore[misc]

    def test_custom_values(self):
        p = PairProfile(
            symbol="CUSTOM",
            base_range_pct=5.0,
            min_range_pct=1.0,
            max_range_pct=20.0,
            atr_multiplier=3.0,
            tags=("test",),
        )
        assert p.base_range_pct == 5.0
        assert p.min_range_pct == 1.0
        assert p.max_range_pct == 20.0
        assert p.atr_multiplier == 3.0
        assert p.tags == ("test",)


# ====================================================================
# PairProfileRegistry
# ====================================================================

class TestPairProfileRegistry:
    def test_default_profiles_loaded(self):
        reg = PairProfileRegistry()
        assert reg.has("XXBTZEUR")
        assert reg.has("XETHZEUR")
        assert reg.has("SOLEUR")
        assert len(reg.symbols) >= 8

    def test_get_known_symbol(self):
        reg = PairProfileRegistry()
        btc = reg.get("XXBTZEUR")
        assert btc.symbol == "XXBTZEUR"
        assert btc.base_range_pct == 2.0
        assert "major" in btc.tags
        assert btc.enable_multi_grid is True

    def test_get_unknown_symbol_returns_fallback(self):
        reg = PairProfileRegistry()
        unknown = reg.get("DOESNOTEXIST")
        assert unknown.symbol == "__fallback__"
        assert unknown.base_range_pct == 3.0

    def test_fallback_preserves_legacy_behaviour(self):
        """Ensure fallback profile remains aligned with current conservative defaults."""
        fb = _FALLBACK_PROFILE
        assert fb.base_range_pct == 3.0
        assert fb.base_num_levels == 15

    def test_custom_profiles_override_defaults(self):
        custom = PairProfile(symbol="XXBTZEUR", base_range_pct=99.0)
        reg = PairProfileRegistry(profiles={"XXBTZEUR": custom})
        assert reg.get("XXBTZEUR").base_range_pct == 99.0

    def test_no_defaults(self):
        reg = PairProfileRegistry(use_defaults=False)
        assert len(reg.symbols) == 0
        assert reg.get("XXBTZEUR") == _FALLBACK_PROFILE

    def test_register_at_runtime(self):
        reg = PairProfileRegistry(use_defaults=False)
        p = PairProfile(symbol="NEW", base_range_pct=3.0)
        reg.register(p)
        assert reg.has("NEW")
        assert reg.get("NEW").base_range_pct == 3.0

    def test_get_all(self):
        reg = PairProfileRegistry()
        all_profiles = reg.get_all()
        assert isinstance(all_profiles, dict)
        assert "XXBTZEUR" in all_profiles

    def test_singleton(self):
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2


# ====================================================================
# DynamicGridAllocator
# ====================================================================

class TestDynamicGridAllocator:
    def setup_method(self):
        self.profile = PairProfile(
            symbol="TEST",
            base_range_pct=6.0,
            min_range_pct=2.0,
            max_range_pct=15.0,
            base_num_levels=15,
            min_levels=5,
            max_levels=30,
            max_capital_per_level=100.0,
            atr_multiplier=2.5,
        )

    # --- compute_num_levels ---

    def test_num_levels_no_atr(self):
        """Without ATR data, returns base_num_levels."""
        assert DynamicGridAllocator.compute_num_levels(self.profile) == 15
        assert DynamicGridAllocator.compute_num_levels(self.profile, None) == 15

    def test_num_levels_low_atr(self):
        """Low ATR -> fewer levels (closer to min)."""
        n = DynamicGridAllocator.compute_num_levels(self.profile, 1.0)
        assert self.profile.min_levels <= n <= self.profile.max_levels
        assert n <= 10  # Should be low

    def test_num_levels_high_atr(self):
        """High ATR -> more levels (closer to max)."""
        n = DynamicGridAllocator.compute_num_levels(self.profile, 10.0)
        assert n >= 20  # Should be high
        assert n <= self.profile.max_levels

    def test_num_levels_clamped(self):
        """Extreme ATR should still respect bounds."""
        n_low = DynamicGridAllocator.compute_num_levels(self.profile, 0.01)
        n_high = DynamicGridAllocator.compute_num_levels(self.profile, 100.0)
        assert n_low >= self.profile.min_levels
        assert n_high <= self.profile.max_levels

    # --- compute_capital_per_level ---

    def test_cpl_basic(self):
        cpl = DynamicGridAllocator.compute_capital_per_level(
            self.profile, available_capital=1000.0, num_levels=15,
        )
        assert 5.0 <= cpl <= 100.0

    def test_cpl_low_capital(self):
        cpl = DynamicGridAllocator.compute_capital_per_level(
            self.profile, available_capital=10.0, num_levels=15,
        )
        assert cpl == 5.0  # Floor

    def test_cpl_zero_capital(self):
        cpl = DynamicGridAllocator.compute_capital_per_level(
            self.profile, available_capital=0.0, num_levels=15,
        )
        assert cpl == 5.0

    def test_cpl_high_vol_reduces_allocation(self):
        cpl_low = DynamicGridAllocator.compute_capital_per_level(
            self.profile, 1000.0, 15, atr_pct=2.0,
        )
        cpl_high = DynamicGridAllocator.compute_capital_per_level(
            self.profile, 1000.0, 15, atr_pct=8.0,
        )
        assert cpl_high < cpl_low

    # --- compute_grid_config ---

    def test_grid_config_complete(self):
        cfg = DynamicGridAllocator.compute_grid_config(
            self.profile, available_capital=1000.0, atr_pct=4.0,
        )
        assert "num_levels" in cfg
        assert "capital_per_level" in cfg
        assert "range_pct" in cfg
        assert self.profile.min_range_pct <= cfg["range_pct"] <= self.profile.max_range_pct

    def test_grid_config_no_atr_uses_base(self):
        cfg = DynamicGridAllocator.compute_grid_config(
            self.profile, available_capital=1000.0,
        )
        assert cfg["range_pct"] == self.profile.base_range_pct
        assert cfg["num_levels"] == self.profile.base_num_levels

    def test_grid_config_range_clamped(self):
        # Very high ATR should not exceed max_range
        cfg = DynamicGridAllocator.compute_grid_config(
            self.profile, available_capital=1000.0, atr_pct=20.0,
        )
        assert cfg["range_pct"] <= self.profile.max_range_pct

        # Very low ATR should not go below min_range
        cfg = DynamicGridAllocator.compute_grid_config(
            self.profile, available_capital=1000.0, atr_pct=0.1,
        )
        assert cfg["range_pct"] >= self.profile.min_range_pct
