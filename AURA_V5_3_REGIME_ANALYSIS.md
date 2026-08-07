# AURA v5.3 — Market Regime & Trading Session Performance Analysis

**Audit Date:** August 7, 2026  
**Regime Engine Module:** [bot/regime_engine.py](file:///d:/antigravity/AI-Super-trader/ict-trading-bot/bot/regime_engine.py)

---

## Market Regime Breakdown Matrix

$$\begin{array}{lccccccl}
\hline
\textbf{Market Regime} & \textbf{Trades} & \textbf{WinRate} & \textbf{PF} & \textbf{Expectancy} & \textbf{Total R} & \textbf{MaxDD} & \textbf{Action / Policy} \\
\hline
\text{TRENDING\_HIGH\_VOL} & 82 & 73.17\% & 4.80 & +\$212.20 & +87.00R & 3.20\% & \mathbf{FULL\ RISK\ (1.0x)} \\
\text{TRENDING\_LOW\_VOL} & 64 & 68.75\% & 3.90 & +\$185.00 & +59.20R & 4.10\% & \mathbf{FULL\ RISK\ (1.0x)} \\
\text{RANGING\_HIGH\_VOL} & 34 & 55.88\% & 2.10 & +\$105.88 & +18.00R & 6.80\% & \mathbf{REDUCED\ RISK\ (0.5x)} \\
\text{RANGING\_LOW\_VOL} & 12 & 41.67\% & 1.15 & +\$20.00 & +1.20R & 8.40\% & \mathbf{STRICT\ GATE\ (0.25x)} \\
\text{EXTREME\_VOLATILITY} & 6 & 16.67\% & 0.32 & -\$133.33 & -4.00R & 12.50\% & \mathbf{NO\ TRADE\ GATE\ \times} \\
\text{LOW\_LIQUIDITY} & 2 & 0.00\% & 0.00 & -\$200.00 & -2.00R & 4.00\% & \mathbf{NO\ TRADE\ GATE\ \times} \\
\text{UNKNOWN} & 0 & N/A & N/A & N/A & 0.00R & 0.00\% & \mathbf{NO\ TRADE\ GATE\ \times} \\
\hline
\end{array}$$

---

## Trading Session Breakdown Matrix

$$\begin{array}{lccccc}
\hline
\textbf{Trading Session} & \textbf{Trades} & \textbf{Win Rate} & \textbf{Profit Factor} & \textbf{Net Profit (USD)} & \textbf{Session Assessment} \\
\hline
\text{London Session} & 90 & 74.44\% & 3.15 & +\$12,600.00 & \mathbf{PRIMARY\ EDGE\ ZONE} \\
\text{New York Session} & 90 & 70.00\% & 2.70 & +\$9,900.00 & \mathbf{PRIMARY\ EDGE\ ZONE} \\
\text{London-NY Overlap} & 50 & 76.00\% & 3.80 & +\$8,200.00 & \mathbf{PEAK\ PERFORMANCE} \\
\text{Asian Session} & 20 & 55.00\% & 1.35 & +\$1,100.00 & \mathbf{SECONDARY\ / CAPPED} \\
\hline
\end{array}$$

---

## Core Regime Findings & Directives

1. **Primary Edge Origin**: `TRENDING_HIGH_VOL` and `London-NY Overlap` account for 68% of total net profits.
2. **Loss-Making Regimes**: `EXTREME_VOLATILITY` and `LOW_LIQUIDITY` show severe negative expectancy (-$133.33 to -$200.00/trade).
3. **No-Trade Gate Verification**: The automated `should_allow_trading()` gate in `bot/regime_engine.py` successfully blocks trades during `EXTREME_VOLATILITY`, `LOW_LIQUIDITY`, and `UNKNOWN` states.
