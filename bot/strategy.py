"""
=====================================================================
 AURA INSTITUTIONAL STRATEGY ENGINE  (v4.0)
=====================================================================
 Core: ICT Order Flow + Volume Imbalance Validation

 Pipeline (ทุก Setup ต้องผ่านครบ):
   1) 4H Shield      — BOS/CHOCH trend gate
   2) Liquidity Sweep — กวาด Session High/Low ก่อน MSS
   3) MSS            — Market Structure Shift บน M15
   4) OB หรือ FVG    — ต้องมี Volume Imbalance บนแท่งที่สร้าง Zone
   5) Killzone Filter — London / NY session (configurable)

 Volume Imbalance:
   volume[candle] >= volume_ma20 * volume_spike_mult (default 1.5x)
=====================================================================
"""

import sys
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
import os
from datetime import datetime, time as dt_time

import numpy as np
import pandas as pd
import pytz
from smartmoneyconcepts import smc

from bot.logger import logger


class ICTStrategy:
    """ICT Order Flow strategy with institutional volume validation."""

    def __init__(self, mt5_client, config):
        self.mt5 = mt5_client
        self.config = config
        self.aura_cfg = config.get("aura_ultimate", {})
        self._ny_tz = pytz.timezone("America/New_York")

    # -----------------------------------------------------------------
    #  ATR & Volume helpers
    # -----------------------------------------------------------------
    @staticmethod
    def calculate_atr(df, period=14):
        high = df["high"]
        low = df["low"]
        close = df["close"]
        tr = pd.concat(
            [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
            axis=1,
        ).max(axis=1)
        return tr.rolling(period).mean().bfill()

    @staticmethod
    def _prepare_df(df):
        df = df.copy()
        if "tick_volume" in df.columns:
            df.rename(columns={"tick_volume": "volume"}, inplace=True)
        if "volume" not in df.columns:
            df["volume"] = 0
        return df

    def _volume_ma_period(self):
        return int(self.aura_cfg.get("volume_ma_period", 20))

    def _volume_spike_mult(self):
        return float(self.aura_cfg.get("volume_spike_mult", 1.5))

    def has_volume_imbalance(self, df, bar_idx):
        """
        ตรวจ Volume Imbalance: ปริมาณแท่ง breakout >= MA(20) * multiplier
        Returns (bool, spike_multiplier)
        """
        period = self._volume_ma_period()
        mult_threshold = self._volume_spike_mult()

        if bar_idx is None or bar_idx < period or bar_idx >= len(df):
            return False, 0.0

        vol_series = df["volume"].astype(float)
        vol_ma = vol_series.rolling(period).mean()
        candle_vol = float(vol_series.iloc[bar_idx])
        ma_val = float(vol_ma.iloc[bar_idx])

        if ma_val <= 0 or candle_vol <= 0:
            return False, 0.0

        spike = candle_vol / ma_val
        return spike >= mult_threshold, round(spike, 3)

    def _trend_strength(self, df, period=14):
        """ADX-lite: ความแรงของเทรนด์จาก normalized ATR / price."""
        if len(df) < period + 2:
            return 0.0
        atr = self.calculate_atr(df, period)
        atr_val = float(atr.iloc[-1])
        price = float(df["close"].iloc[-1])
        if price <= 0 or pd.isna(atr_val):
            return 0.0
        return round(min(atr_val / price * 1000, 10.0), 3)

    # -----------------------------------------------------------------
    #  4H SHIELD
    # -----------------------------------------------------------------
    def analyze_market_structure(self, symbol):
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

    def get_htf_premium_discount_zone(self, symbol, df_h4=None):
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
    #  MSS Detection (M15)
    # -----------------------------------------------------------------
    @staticmethod
    def _detect_mss(df, want_direction=1):
        """
        Market Structure Shift บน LTF
        want_direction: 1 = bullish MSS, -1 = bearish MSS
        Returns (bool, bar_idx)
        """
        try:
            swing = smc.swing_highs_lows(df)
            if swing is None or swing.empty:
                return False, None
            mss = smc.bos_choch(df, swing)
            if mss is None or mss.empty:
                return False, None

            recent = mss.tail(30)
            for idx in reversed(recent.index):
                row = recent.loc[idx]
                bos = row.get("BOS", 0)
                choch = row.get("CHOCH", 0)
                if want_direction == 1 and (bos == 1 or choch == 1):
                    return True, idx
                if want_direction == -1 and (bos == -1 or choch == -1):
                    return True, idx
            return False, None
        except Exception:
            return False, None

    # -----------------------------------------------------------------
    #  Session Liquidity Sweep (Killzone-aware)
    # -----------------------------------------------------------------
    def _parse_session_window(self, session_cfg):
        start = datetime.strptime(session_cfg["start"], "%H:%M").time()
        end = datetime.strptime(session_cfg["end"], "%H:%M").time()
        return start, end

    def _bars_in_ny_session(self, df, session_name):
        """กรองแท่งที่อยู่ใน Killzone (NY time)"""
        kz = self.config.get("killzones_ny_time", {})
        if session_name not in kz or not kz[session_name].get("enabled", True):
            return pd.DataFrame()

        start_t, end_t = self._parse_session_window(kz[session_name])
        if "time" not in df.columns:
            return pd.DataFrame()

        times = pd.to_datetime(df["time"])
        if times.dt.tz is None:
            times = times.dt.tz_localize("UTC")
        ny_times = times.dt.tz_convert(self._ny_tz)
        bar_times = ny_times.dt.time

        if start_t <= end_t:
            mask = (bar_times >= start_t) & (bar_times <= end_t)
        else:
            mask = (bar_times >= start_t) | (bar_times <= end_t)

        return df.loc[mask.values]

    def _detect_session_liquidity_sweep(self, df, want_direction=1, lookback=80):
        """
        ตรวจ Liquidity Sweep ของ Session High/Low ก่อน MSS (Strict Temporal Integrity)
        Bull: ราคากวาดต่ำกว่า session low แล้วปิดกลับเหนือ
        Bear: ราคากวาดสูงกว่า session high แล้วปิดกลับต่ำกว่า
        """
        if len(df) < lookback + 5:
            return None

        recent = df.tail(lookback).copy()
        sweep_window = recent.tail(15)

        for idx in sweep_window.index:
            history_before_idx = recent.loc[:idx].iloc[:-1]
            if len(history_before_idx) < 10:
                continue

            session_bars = pd.concat([
                self._bars_in_ny_session(history_before_idx, "london"),
                self._bars_in_ny_session(history_before_idx, "new_york"),
            ]).drop_duplicates()

            if session_bars.empty:
                session_high = history_before_idx["high"].max()
                session_low = history_before_idx["low"].min()
            else:
                session_high = session_bars["high"].max()
                session_low = session_bars["low"].min()

            bar = recent.loc[idx]
            if want_direction == 1:
                if bar["low"] < session_low and bar["close"] > session_low:
                    return "bull_sweep"
            else:
                if bar["high"] > session_high and bar["close"] < session_high:
                    return "bear_sweep"
        return None

    @staticmethod
    def _detect_sweep(df, lookback=20):
        """Legacy sweep detector — ใช้เป็น fallback"""
        try:
            if len(df) < lookback + 2:
                return None
            recent = df.tail(lookback + 1)
            swing_low = recent["low"].min()
            swing_high = recent["high"].max()
            last_bar = df.iloc[-1]

            if last_bar["low"] < swing_low and last_bar["close"] > swing_low:
                return "bull_sweep"
            if last_bar["high"] > swing_high and last_bar["close"] < swing_high:
                return "bear_sweep"
            return None
        except Exception:
            return None

    # -----------------------------------------------------------------
    #  OB / FVG with Volume Validation
    # -----------------------------------------------------------------
    @staticmethod
    def _detect_ob(df):
        try:
            swing = smc.swing_highs_lows(df)
            if swing is None or swing.empty:
                return []
            ob_df = smc.ob(df, swing)
            if ob_df is None or ob_df.empty:
                return []
            results = []
            for _, row in ob_df.iterrows():
                ob_type = (
                    "bull" if row.get("OB", 0) == 1
                    else "bear" if row.get("OB", 0) == -1
                    else None
                )
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

    @staticmethod
    def _fvg(df):
        try:
            return smc.fvg(df)
        except Exception:
            return pd.DataFrame()

    @staticmethod
    def _resolve_bar_idx(df, idx):
        if idx is None:
            return None
        if isinstance(idx, (int, np.integer)):
            return int(idx) if 0 <= idx < len(df) else None
        try:
            loc = df.index.get_loc(idx)
            if isinstance(loc, slice):
                return loc.start
            if isinstance(loc, np.ndarray):
                return int(loc[0]) if len(loc) else None
            return int(loc)
        except Exception:
            return None

    def _get_valid_fvg(self, df, want_d, min_size, atr_val):
        """FVG ที่ผ่าน Volume Imbalance + ขนาดขั้นต่ำ"""
        fvg_df = self._fvg(df)
        if fvg_df is None or fvg_df.empty:
            return None

        valid = fvg_df[fvg_df["FVG"].notna()]
        want_type = "bull" if want_d == 1 else "bear"

        for _, row in valid.iloc[::-1].iterrows():
            fvg_type = "bull" if row["FVG"] == 1 else "bear"
            if fvg_type != want_type:
                continue

            top = float(row["Top"])
            bot = float(row["Bottom"])
            size = abs(top - bot)
            if size < min_size:
                continue

            bar_idx = self._resolve_bar_idx(df, row.name)
            # FVG middle candle = bar before gap completion
            creation_idx = bar_idx - 1 if bar_idx is not None and bar_idx > 0 else bar_idx
            ok, spike = self.has_volume_imbalance(df, creation_idx)
            if not ok:
                logger.debug(f"FVG rejected: no volume imbalance (spike={spike})")
                continue

            return {
                "type": fvg_type,
                "top": top,
                "bottom": bot,
                "size": size,
                "bar_idx": bar_idx,
                "volume_spike": spike,
            }
        return None

    def _get_valid_ob(self, df, want_d):
        """Order Block ที่ผ่าน Volume Imbalance"""
        obs = self._detect_ob(df)
        want_type = "bull" if want_d == 1 else "bear"

        for ob in reversed(obs):
            if ob["type"] != want_type:
                continue
            bar_idx = self._resolve_bar_idx(df, ob["bar_idx"])
            ok, spike = self.has_volume_imbalance(df, bar_idx)
            if not ok:
                logger.debug(f"OB rejected: no volume imbalance (spike={spike})")
                continue
            ob["volume_spike"] = spike
            ob["bar_idx"] = bar_idx
            return ob
        return None

    # -----------------------------------------------------------------
    #  Setup Builders
    # -----------------------------------------------------------------
    def _build_order_flow_setup(self, df, trend, atr_val, tick, symbol):
        """
        Institutional Order Flow Setup:
          Sweep → MSS → (OB and/or FVG) → Volume Imbalance
        """
        want_d = 1 if trend == "BULLISH" else -1
        fvg_mult = self.aura_cfg.get("fvg_atr_mult", 0.5)
        min_fvg = atr_val * fvg_mult

        # 1) Liquidity Sweep ก่อน MSS
        sweep = self._detect_session_liquidity_sweep(df, want_d)
        if sweep is None:
            sweep = self._detect_sweep(df, self.aura_cfg.get("ob_lookback", 20))
        if sweep is None:
            return None
        if want_d == 1 and sweep != "bull_sweep":
            return None
        if want_d == -1 and sweep != "bear_sweep":
            return None

        # 2) MSS confirmation
        mss_ok, mss_idx = self._detect_mss(df, want_d)
        if not mss_ok:
            return None

        # 3) OB และ/หรือ FVG พร้อม Volume Imbalance
        ob_match = self._get_valid_ob(df, want_d)
        fvg_match = self._get_valid_fvg(df, want_d, min_fvg, atr_val)

        if ob_match is None and fvg_match is None:
            return None

        is_full_confluence = ob_match is not None and fvg_match is not None
        rr_key = "sniper_rr" if is_full_confluence else "base_rr"
        rr = self.aura_cfg.get(rr_key, 3.5 if is_full_confluence else 2.5)

        ask = tick.ask
        bid = tick.bid
        trend_str = self._trend_strength(df)

        if want_d == 1:
            fvg_bot = fvg_match["bottom"] if fvg_match else (ob_match["bottom"] if ob_match else ask)
            ob_bot = ob_match["bottom"] if ob_match else fvg_bot
            entry = max(ask, fvg_bot)
            sl = min(ob_bot, fvg_bot) - atr_val * 0.5
            risk = abs(entry - sl)
            if risk <= 0:
                return None
            tp = entry + risk * rr
            source = "Order Flow Sniper (Sweep+MSS+OB+FVG+Vol)" if is_full_confluence else (
                "Order Flow OB (Sweep+MSS+Vol)" if ob_match and not fvg_match
                else "Order Flow FVG (Sweep+MSS+Vol)"
            )
            return {
                "type": "BUY",
                "source": source,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "tp1": tp,
                "is_sniper": is_full_confluence,
                "ob_zone": [ob_match["bottom"], ob_match["top"]] if ob_match else None,
                "fvg_zone": [fvg_match["bottom"], fvg_match["top"]] if fvg_match else None,
                "fvg_size": fvg_match["size"] if fvg_match else 0.0,
                "sweep": sweep,
                "mss_confirmed": True,
                "volume_spike": max(
                    ob_match.get("volume_spike", 0) if ob_match else 0,
                    fvg_match.get("volume_spike", 0) if fvg_match else 0,
                ),
                "trend_strength": trend_str,
            }

        fvg_top = fvg_match["top"] if fvg_match else (ob_match["top"] if ob_match else bid)
        ob_top = ob_match["top"] if ob_match else fvg_top
        entry = min(bid, fvg_top)
        sl = max(ob_top, fvg_top) + atr_val * 0.5
        risk = abs(sl - entry)
        if risk <= 0:
            return None
        tp = entry - risk * rr
        source = "Order Flow Sniper (Sweep+MSS+OB+FVG+Vol)" if is_full_confluence else (
            "Order Flow OB (Sweep+MSS+Vol)" if ob_match and not fvg_match
            else "Order Flow FVG (Sweep+MSS+Vol)"
        )
        return {
            "type": "SELL",
            "source": source,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "tp1": tp,
            "is_sniper": is_full_confluence,
            "ob_zone": [ob_match["bottom"], ob_match["top"]] if ob_match else None,
            "fvg_zone": [fvg_match["bottom"], fvg_match["top"]] if fvg_match else None,
            "fvg_size": fvg_match["size"] if fvg_match else 0.0,
            "sweep": sweep,
            "mss_confirmed": True,
            "volume_spike": max(
                ob_match.get("volume_spike", 0) if ob_match else 0,
                fvg_match.get("volume_spike", 0) if fvg_match else 0,
            ),
            "trend_strength": trend_str,
        }

    # -----------------------------------------------------------------
    #  Main Entry Point
    # -----------------------------------------------------------------
    def find_super_trader_setup(self, symbol, trend, df_m15=None, df_h4=None):
        """
        AURA v4.0 — Institutional Order Flow only.
        ไม่มี Base FVG fallback: ทุกสัญญาณต้องผ่าน Volume Imbalance
        """
        if trend == "NEUTRAL":
            return None

        df = (
            df_m15 if df_m15 is not None and not df_m15.empty
            else self.mt5.get_rates(symbol, "M15", 250)
        )
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

            setup = self._build_order_flow_setup(df, trend, atr_val, tick, symbol)
            if setup:
                setup["symbol"] = symbol
            return setup

        except Exception as e:
            logger.error(f"Error in Order Flow setup for {symbol}: {e}")
            return None

    # -----------------------------------------------------------------
    #  Killzone Filter
    # -----------------------------------------------------------------
    def is_in_killzone(self):
        """
        ตรวจว่าอยู่ใน Killzone (London / NY) หรือไม่
        ถ้า all_day_scalping = true → เปิดตลอด (backward compat)
        """
        if self.aura_cfg.get("all_day_scalping", False):
            return True, "ALL_DAY_SCALPING"

        kz = self.config.get("killzones_ny_time", {})
        now_ny = datetime.now(self._ny_tz).time()

        for session_name, cfg in kz.items():
            if not cfg.get("enabled", True):
                continue
            start_t, end_t = self._parse_session_window(cfg)
            if start_t <= end_t:
                in_zone = start_t <= now_ny <= end_t
            else:
                in_zone = now_ny >= start_t or now_ny <= end_t
            if in_zone:
                return True, session_name.upper()

        return False, "OUTSIDE_KILLZONE"
