"""
=====================================================================
 AURA ULTIMATE STRATEGY ENGINE  (v3.0)  -  Core Engine Rewrite
=========================================================
 Merge: Strategy 3 MTF 4H Shield + Sniper OB/Sweep/FVG
 - 4H Shield: HTF trend gate (HH/HL or LH/LL via BOS/CHOCH)
 - LTF FVG: M15 Fair Value Gap with directional filter
 - Sniper: OB + Liquidity Sweep + FVG confluence (high-precision)
 - Base: FVG-only fallback (wider net)
=====================================================================
"""

import pandas as pd
import numpy as np
from smartmoneyconcepts import smc
from bot.logger import logger
from datetime import datetime
import pytz
import math


class ICTStrategy:
    def __init__(self, mt5_client, config):
        self.mt5 = mt5_client
        self.config = config
        self.aura_cfg = config.get("aura_ultimate", {})

    # -----------------------------------------------------------------
    #  ATR helper
    # -----------------------------------------------------------------
    def calculate_atr(self, df, period=14):
        high = df["high"]
        low = df["low"]
        close = df["close"]
        tr = pd.concat(
            [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
            axis=1,
        ).max(axis=1)
        return tr.rolling(period).mean().bfill()

    # -----------------------------------------------------------------
    #  Internal helpers
    # -----------------------------------------------------------------
    @staticmethod
    def _prepare_df(df):
        """Ensure column names are standardised and volume exists."""
        df = df.copy()
        if "tick_volume" in df.columns:
            df.rename(columns={"tick_volume": "volume"}, inplace=True)
        if "volume" not in df.columns:
            df["volume"] = 0
        return df

    # -----------------------------------------------------------------
    #  4H SHIELD  -  MTF Trend Gate
    # -----------------------------------------------------------------
    def analyze_market_structure(self, symbol):
        """
        Strategy 3 - MTF 4H Trend Shield:
          1) Detect bullish structure (HH/HL) or bearish (LH/LL) on H4
          2) Use BOS / CHOCH signals
          3) Return BULLISH / BEARISH / NEUTRAL
        """
        df_h4 = self.mt5.get_rates(symbol, "H4", 500)
        if df_h4 is None or df_h4.empty:
            return "NEUTRAL"

        df_h4 = self._prepare_df(df_h4)

        swing_h4 = smc.swing_highs_lows(df_h4)
        if swing_h4 is None or swing_h4.empty:
            return "NEUTRAL"

        mss_h4 = smc.bos_choch(df_h4, swing_h4)
        if mss_h4 is None or mss_h4.empty:
            return "NEUTRAL"

        v_bos = mss_h4[mss_h4["BOS"].isin([1, -1])].tail(1)
        v_choch = mss_h4[mss_h4["CHOCH"].isin([1, -1])].tail(1)

        trend = "NEUTRAL"
        if not v_bos.empty:
            trend = "BULLISH" if v_bos["BOS"].iloc[0] == 1 else "BEARISH"
        if not v_choch.empty and (
            v_bos.empty or v_choch.index[0] > v_bos.index[0]
        ):
            trend = "BULLISH" if v_choch["CHOCH"].iloc[0] == 1 else "BEARISH"

        return trend

    # -----------------------------------------------------------------
    #  HTF Premium / Discount Zone
    # -----------------------------------------------------------------
    def get_htf_premium_discount_zone(self, symbol, df_h4=None):
        """
        50 % Fibonacci Equilibrium ของ 4H range.
        DISCOUNT < 50 %  -> BUY zone
        PREMIUM   > 50 % -> SELL zone
        """
        try:
            if df_h4 is None or df_h4.empty:
                df_h4 = self.mt5.get_rates(symbol, "H4", 500)
            if df_h4 is None or df_h4.empty:
                return "NEUTRAL"

            h4_high = df_h4["high"].tail(30).max()
            h4_low = df_h4["low"].tail(30).min()
            h4_range = h4_high - h4_low
            if h4_range <= 0:
                return "NEUTRAL"

            equilibrium = h4_low + h4_range * 0.5
            c_close = df_h4["close"].iloc[-1]
            return "DISCOUNT" if c_close < equilibrium else "PREMIUM"
        except Exception as e:
            logger.error(f"Error calculating HTF zone for {symbol}: {e}")
            return "NEUTRAL"

    # -----------------------------------------------------------------
    #  Order Block Detection  (using smartmoneyconcepts)
    # -----------------------------------------------------------------
    @staticmethod
    def _detect_ob(df):
        """Return list of OB dicts [{'type': 'bull'/'bear', 'top': .., 'bottom': .., 'bar_idx': ..}]"""
        try:
            swing = smc.swing_highs_lows(df)
            if swing is None or swing.empty:
                return []
            ob_df = smc.ob(df, swing)
            if ob_df is None or ob_df.empty:
                return []
            results = []
            for _, row in ob_df.iterrows():
                ob_type = "bull" if row.get("OB", 0) == 1 else "bear" if row.get("OB", 0) == -1 else None
                if ob_type:
                    results.append({
                        "type": ob_type,
                        "top": row.get("Top", row.get("top", 0)),
                        "bottom": row.get("Bottom", row.get("bottom", 0)),
                        "bar_idx": row.name,
                    })
            return results
        except Exception:
            return []

    # -----------------------------------------------------------------
    #  Liquidity Sweep Detection
    # -----------------------------------------------------------------
    @staticmethod
    def _detect_sweep(df, lookback=20):
        """
        Detect if the most recent bars swept below a recent swing low (bullish sweep)
        or above a recent swing high (bearish sweep).
        Returns 'bull_sweep' / 'bear_sweep' / None
        """
        try:
            if len(df) < lookback + 2:
                return None
            recent = df.tail(lookback + 1)
            swing_low = recent["low"].min()
            swing_high = recent["high"].max()
            last_bar = df.iloc[-1]
            prev_bars = df.iloc[-(lookback):-1]

            # Bullish sweep: last bar low < recent swing low, then close above it
            if last_bar["low"] < swing_low and last_bar["close"] > swing_low:
                return "bull_sweep"
            # Bearish sweep: last bar high > recent swing high, then close below it
            if last_bar["high"] > swing_high and last_bar["close"] < swing_high:
                return "bear_sweep"
            return None
        except Exception:
            return None

    # -----------------------------------------------------------------
    #  FVG Detection (directional)
    # -----------------------------------------------------------------
    @staticmethod
    def _fvg(df):
        """Return smc FVG dataframe with Top/Bottom/FVG columns."""
        try:
            return smc.fvg(df)
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _get_last_valid_fvg(fvg_df, min_size=0):
        """Get the last FVG that meets min_size. Returns dict or None."""
        if fvg_df is None or fvg_df.empty:
            return None
        valid = fvg_df[fvg_df["FVG"].notna()]
        if valid.empty:
            return None
        for _, row in valid.iloc[::-1].iterrows():
            top = row["Top"]
            bot = row["Bottom"]
            size = abs(top - bot)
            if size >= min_size:
                return {
                    "type": "bull" if row["FVG"] == 1 else "bear",
                    "top": top,
                    "bottom": bot,
                    "size": size,
                    "bar_idx": row.name,
                }
        return None

    # -----------------------------------------------------------------
    #  Sniper Entry  (OB + Sweep + FVG confluence)
    # -----------------------------------------------------------------
    def _build_sniper_setup(self, df, trend, atr_val, tick, symbol):
        """
        Sniper: requires Order Block + Liquidity Sweep + FVG all present
        and aligned with the trend direction.
        Returns setup dict or None.
        """
        want_d = 1 if trend == "BULLISH" else -1

        # --- Order Block ---
        obs = self._detect_ob(df)
        ob_match = None
        for ob in reversed(obs):
            if ob["type"] == ("bull" if want_d == 1 else "bear"):
                ob_match = ob
                break
        if ob_match is None:
            return None

        # --- Liquidity Sweep ---
        sweep = self._detect_sweep(df)
        if sweep is None:
            return None
        if want_d == 1 and sweep != "bull_sweep":
            return None
        if want_d == -1 and sweep != "bear_sweep":
            return None

        # --- FVG (directional) ---
        fvg_mult = self.aura_cfg.get("fvg_atr_mult", 0.25)
        min_fvg = atr_val * fvg_mult
        fvg_df = self._fvg(df)
        last_fvg = self._get_last_valid_fvg(fvg_df, min_size=min_fvg)
        if last_fvg is None:
            return None
        if last_fvg["type"] != ("bull" if want_d == 1 else "bear"):
            return None

        # --- Build entry ---
        ask = tick.ask
        bid = tick.bid
        if want_d == 1:
            entry = max(ask, last_fvg["bottom"])
            sl = min(ob_match["bottom"], last_fvg["bottom"]) - atr_val * 0.5
            risk = abs(entry - sl)
            if risk <= 0:
                return None
            tp = entry + risk * self.aura_cfg.get("sniper_rr", 3.0)
            return {
                "type": "BUY",
                "source": "Sniper (OB+Sweep+FVG)",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "tp1": tp,
                "is_sniper": True,
                "ob_zone": [ob_match["bottom"], ob_match["top"]],
                "fvg_zone": [last_fvg["bottom"], last_fvg["top"]],
                "sweep": sweep,
            }
        else:
            entry = min(bid, last_fvg["top"])
            sl = max(ob_match["top"], last_fvg["top"]) + atr_val * 0.5
            risk = abs(sl - entry)
            if risk <= 0:
                return None
            tp = entry - risk * self.aura_cfg.get("sniper_rr", 3.0)
            return {
                "type": "SELL",
                "source": "Sniper (OB+Sweep+FVG)",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "tp1": tp,
                "is_sniper": True,
                "ob_zone": [ob_match["bottom"], ob_match["top"]],
                "fvg_zone": [last_fvg["bottom"], last_fvg["top"]],
                "sweep": sweep,
            }

    # -----------------------------------------------------------------
    #  OB+FVG Setup  (OB + FVG, no sweep required)
    # -----------------------------------------------------------------
    def _build_ob_fvg_setup(self, df, trend, atr_val, tick, symbol):
        """
        OB+FVG: requires Order Block + FVG (no sweep needed).
        Higher quality than Base FVG alone, more common than full Sniper.
        """
        want_d = 1 if trend == "BULLISH" else -1

        # --- Order Block (any direction, but prefer aligned) ---
        obs = self._detect_ob(df)
        ob_match = None
        for ob in reversed(obs):
            if ob["type"] == ("bull" if want_d == 1 else "bear"):
                ob_match = ob
                break
        # If no aligned OB, try any OB (counter-trend OB as support)
        if ob_match is None and obs:
            ob_match = obs[-1]
        if ob_match is None:
            return None

        # --- FVG (directional) ---
        fvg_mult = self.aura_cfg.get("fvg_atr_mult", 0.25)
        min_fvg = atr_val * fvg_mult
        fvg_df = self._fvg(df)
        last_fvg = self._get_last_valid_fvg(fvg_df, min_size=min_fvg)
        if last_fvg is None:
            return None
        if last_fvg["type"] != ("bull" if want_d == 1 else "bear"):
            return None

        ask = tick.ask
        bid = tick.bid
        if want_d == 1:
            entry = max(ask, last_fvg["bottom"])
            sl = min(ob_match["bottom"], last_fvg["bottom"]) - atr_val * 0.8
            risk = abs(entry - sl)
            if risk <= 0:
                return None
            tp = entry + risk * self.aura_cfg.get("base_rr", 4.0)
            return {
                "type": "BUY",
                "source": "OB+FVG",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "tp1": tp,
                "is_sniper": False,
                "ob_zone": [ob_match["bottom"], ob_match["top"]],
                "fvg_zone": [last_fvg["bottom"], last_fvg["top"]],
            }
        else:
            entry = min(bid, last_fvg["top"])
            sl = max(ob_match["top"], last_fvg["top"]) + atr_val * 0.8
            risk = abs(sl - entry)
            if risk <= 0:
                return None
            tp = entry - risk * self.aura_cfg.get("base_rr", 4.0)
            return {
                "type": "SELL",
                "source": "OB+FVG",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "tp1": tp,
                "is_sniper": False,
                "ob_zone": [ob_match["bottom"], ob_match["top"]],
                "fvg_zone": [last_fvg["bottom"], last_fvg["top"]],
            }

    # -----------------------------------------------------------------
    #  Base Setup  (FVG only, directional filter)
    # -----------------------------------------------------------------
    def _build_base_setup(self, df, trend, atr_val, tick, symbol):
        """
        Base setup: FVG-only with directional filter.
        Fallback when Sniper conditions are not met.
        """
        want_d = 1 if trend == "BULLISH" else -1
        fvg_mult = self.aura_cfg.get("fvg_atr_mult", 0.25)
        min_fvg = atr_val * fvg_mult
        fvg_df = self._fvg(df)
        last_fvg = self._get_last_valid_fvg(fvg_df, min_size=min_fvg)
        if last_fvg is None:
            return None
        if last_fvg["type"] != ("bull" if want_d == 1 else "bear"):
            return None

        ask = tick.ask
        bid = tick.bid
        if want_d == 1:
            entry = max(ask, last_fvg["bottom"])
            sl = last_fvg["bottom"] - atr_val * 0.8
            risk = abs(entry - sl)
            if risk <= 0:
                return None
            tp = entry + risk * self.aura_cfg.get("base_rr", 4.0)
            return {
                "type": "BUY",
                "source": "Base FVG",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "tp1": tp,
                "is_sniper": False,
                "fvg_zone": [last_fvg["bottom"], last_fvg["top"]],
            }
        else:
            entry = min(bid, last_fvg["top"])
            sl = last_fvg["top"] + atr_val * 0.8
            risk = abs(sl - entry)
            if risk <= 0:
                return None
            tp = entry - risk * self.aura_cfg.get("base_rr", 4.0)
            return {
                "type": "SELL",
                "source": "Base FVG",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "tp1": tp,
                "is_sniper": False,
                "fvg_zone": [last_fvg["bottom"], last_fvg["top"]],
            }

    # -----------------------------------------------------------------
    #  find_super_trader_setup  (main entry point)
    # -----------------------------------------------------------------
    def find_super_trader_setup(self, symbol, trend, df_m15=None, df_h4=None):
        """
        AURA Ultimate entry logic:
          1) Get M15 data
          2) Compute ATR
          3) Try Sniper first (OB + Sweep + FVG)
          4) If Sniper fails, try OB+FVG (OB + FVG, no sweep)
          5) If OB+FVG fails, try Base (FVG only)
          6) All require directional alignment with 4H trend
        """
        if trend == "NEUTRAL":
            return None

        df = df_m15 if df_m15 is not None and not df_m15.empty else self.mt5.get_rates(symbol, "M15", 250)
        if df is None or df.empty:
            return None

        df = self._prepare_df(df)
        df["atr"] = self.calculate_atr(df, 14)
        atr_val = df["atr"].iloc[-1]
        if pd.isna(atr_val) or atr_val <= 0:
            return None

        try:
            tick = self.mt5.get_tick(symbol)
            if not tick:
                return None

            # --- Sniper first (OB + Sweep + FVG) ---
            setup = self._build_sniper_setup(df, trend, atr_val, tick, symbol)
            if setup is not None:
                return setup

            # --- Base fallback (FVG only) ---
            setup = self._build_base_setup(df, trend, atr_val, tick, symbol)
            return setup

        except Exception as e:
            logger.error(f"Error in AURA Ultimate setup for {symbol}: {e}")
            return None

    # -----------------------------------------------------------------
    #  Killzone  (pass-through for ALL_DAY_SCALPING mode)
    # -----------------------------------------------------------------
    def is_in_killzone(self):
        return True, "ALL_DAY_SCALPING"
