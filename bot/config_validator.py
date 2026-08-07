"""
Production-Grade Configuration Hierarchy & Fail-Fast Validator (AURA v5)
========================================================================
Enforces Single Source of Truth Configuration from bot/config.json.
Fail-Fast Architecture: Rejects invalid, missing, or out-of-range parameters.
"""

from __future__ import annotations
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger


class ConfigurationValidationError(ValueError):
    """Raised when configuration fails schema validation or contains out-of-range parameters."""
    pass


@dataclass
class ValidatedSystemConfig:
    risk_per_trade_percent: float
    daily_drawdown_limit_percent: float
    max_total_open_orders: int
    max_orders_per_symbol: int
    max_same_currency_exposure: int
    min_rr_ratio: float
    ml_threshold: float
    symbols: List[str]
    max_spread_points: Dict[str, int]
    raw_config: Dict[str, Any] = field(default_factory=dict)


class SystemConfigValidator:
    """
    Validates bot/config.json against strict quant boundaries.
    """

    ALLOWED_RANGES = {
        "risk_per_trade_percent": (0.1, 5.0),
        "daily_drawdown_limit_percent": (1.0, 15.0),
        "max_total_open_orders": (1, 20),
        "max_orders_per_symbol": (1, 5),
        "max_same_currency_exposure": (1, 5),
        "min_rr_ratio": (1.0, 10.0),
        "ml_threshold": (0.50, 0.90)
    }

    MANDATORY_KEYS = [
        "risk_per_trade_percent",
        "daily_drawdown_limit_percent",
        "max_total_open_orders",
        "max_orders_per_symbol",
        "max_same_currency_exposure",
        "min_rr_ratio",
        "symbols"
    ]

    @classmethod
    def load_and_validate(cls, config_path: Optional[Path] = None) -> ValidatedSystemConfig:
        """Loads and validates configuration. Fails fast on invalid schemas."""
        cfg_file = config_path or (Path(__file__).resolve().parent / "config.json")
        
        if not cfg_file.exists():
            raise ConfigurationValidationError(f"FAIL-FAST: Config file not found at {cfg_file}")

        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                raw_cfg = json.load(f)
        except Exception as e:
            raise ConfigurationValidationError(f"FAIL-FAST: Corrupted JSON config: {e}")

        return cls.validate_dict(raw_cfg)

    @classmethod
    def validate_dict(cls, raw_cfg: Dict[str, Any]) -> ValidatedSystemConfig:
        """Validates configuration dictionary against boundaries."""
        # 1. Missing Mandatory Keys Check
        for key in cls.MANDATORY_KEYS:
            if key not in raw_cfg:
                raise ConfigurationValidationError(f"FAIL-FAST: Missing mandatory config key '{key}'")

        # 2. Type & Range Validation
        for param, (min_v, max_v) in cls.ALLOWED_RANGES.items():
            if param in raw_cfg:
                val = float(raw_cfg[param])
                if val < min_v or val > max_v:
                    raise ConfigurationValidationError(
                        f"FAIL-FAST: Parameter '{param}' value {val} is out of allowed range [{min_v}, {max_v}]!"
                    )

        # 3. Symbols Check
        symbols = raw_cfg.get("symbols", [])
        if not isinstance(symbols, list) or len(symbols) == 0:
            raise ConfigurationValidationError("FAIL-FAST: 'symbols' list cannot be empty!")

        # 4. Construct ValidatedConfig
        return ValidatedSystemConfig(
            risk_per_trade_percent=float(raw_cfg["risk_per_trade_percent"]),
            daily_drawdown_limit_percent=float(raw_cfg["daily_drawdown_limit_percent"]),
            max_total_open_orders=int(raw_cfg["max_total_open_orders"]),
            max_orders_per_symbol=int(raw_cfg["max_orders_per_symbol"]),
            max_same_currency_exposure=int(raw_cfg["max_same_currency_exposure"]),
            min_rr_ratio=float(raw_cfg["min_rr_ratio"]),
            ml_threshold=float(raw_cfg.get("ml_threshold", 0.60)),
            symbols=list(symbols),
            max_spread_points=raw_cfg.get("max_spread_points", {}),
            raw_config=raw_cfg
        )
