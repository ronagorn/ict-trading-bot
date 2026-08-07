# AURA v5.3 — Risk State Machine & Drift Monitoring Specification

**Audit Date:** August 7, 2026  
**Risk Engine Module:** [bot/risk_manager.py](file:///d:/antigravity/AI-Super-trader/ict-trading-bot/bot/risk_manager.py)  
**No-Trade Engine Module:** [bot/no_trade_engine.py](file:///d:/antigravity/AI-Super-trader/ict-trading-bot/bot/no_trade_engine.py)

---

## Portfolio Risk State Machine Specification

$$\begin{array}{lcccc}
\hline
\textbf{Risk State} & \textbf{Drawdown Trigger} & \textbf{Risk Multiplier} & \textbf{Max New Trades} & \textbf{Recovery Condition} \\
\hline
\mathbf{NORMAL} & \text{Daily DD } < 1.5\% & \mathbf{1.00x\ (100\%)} & 4 & \text{All systems normal} \\
\mathbf{CAUTION} & \text{Daily DD } 1.5\% - 2.5\% & \mathbf{0.75x\ (75\%)} & 2 & \text{Equity returns above 1.5\% DD} \\
\mathbf{DEFENSIVE} & \text{Daily DD } 2.5\% - 3.0\% & \mathbf{0.50x\ (50\%)} & 1 & \text{Equity returns above 2.5\% DD} \\
\mathbf{HALT} & \text{Daily DD } \ge 3.0\% & \mathbf{0.00x\ (0\%)} & 0 & \text{24-Hour Reset + Manual Audit} \\
\hline
\end{array}$$

---

## Drift Monitoring Specification & Alert Gates

| Metric Tracked | Normal Boundary | Warning Boundary | Critical Boundary | Action Triggered |
| :--- | :---: | :---: | :---: | :--- |
| **Feature PSI (Drift)** | $\text{PSI} < 0.10$ | $0.10 \le \text{PSI} < 0.25$ | $\text{PSI} \ge 0.25$ | **WARNING** $\rightarrow$ 50% Lot; **CRITICAL** $\rightarrow$ `STRICT_MODE` |
| **Win Rate Drift** | $\text{WR} \ge 50\%$ | $40\% \le \text{WR} < 50\%$ | $\text{WR} < 40\%$ | **CRITICAL** $\rightarrow$ Trigger Retrain Re-validation Gate |
| **Expectancy Drift** | $+\$150+$ | $+\$50 \rightarrow +\$150$ | $<\$0$ | **CRITICAL** $\rightarrow$ Pause Trading (`STRICT_MODE`) |
| **Data Freshness** | $< 10\text{s}$ | $10\text{s} \rightarrow 60\text{s}$ | $> 60\text{s}$ | **CRITICAL** $\rightarrow$ Block Orders (`NO_TRADE`) |
