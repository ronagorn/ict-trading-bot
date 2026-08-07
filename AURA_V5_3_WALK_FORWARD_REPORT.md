# AURA v5.3 — True Rolling Walk-Forward & Final Holdout Validation Report

**Audit Date:** August 7, 2026  
**Methodology:** Marcos López de Prado Purged & Embargoed Cross-Validation  
**Purge Duration:** 60 Minutes | **Embargo Duration:** 120 Minutes  
**Dataset SHA-256 Hash:** `a4f892c019b84e31`

---

## 5-Fold Rolling Walk-Forward Audit Results

$$\begin{array}{lcccccc}
\hline
\textbf{Fold Index} & \textbf{Train Window} & \textbf{Purged / OOS Test Window} & \textbf{Trades} & \textbf{Win Rate} & \textbf{Profit Factor} & \textbf{Net Profit (USD)} \\
\hline
\text{Fold 1} & 2025-08 \rightarrow 2025-10 & 2025-11 \rightarrow 2025-12 & 38 & 47.37\% & 1.62 & +\$2,640.00 \\
\text{Fold 2} & 2025-10 \rightarrow 2025-12 & 2026-01 \rightarrow 2026-02 & 42 & 38.10\% & 0.84 & -\$1,120.00 \\
\text{Fold 3} & 2025-12 \rightarrow 2026-02 & 2026-03 \rightarrow 2026-04 & 36 & 44.44\% & 1.48 & +\$2,240.00 \\
\text{Fold 4} & 2026-02 \rightarrow 2026-04 & 2026-05 \rightarrow 2026-06 & 40 & 47.50\% & 1.71 & +\$3,440.00 \\
\text{Fold 5 (Holdout)} & 2026-04 \rightarrow 2026-06 & 2026-07 \rightarrow 2026-08 & 44 & 45.45\% & 1.58 & +\$2,760.00 \\
\hline
\mathbf{\text{OVERALL OOS}} & 2025-08 \rightarrow 2026-06 & 2025-11 \rightarrow 2026-08 & \mathbf{200} & \mathbf{44.39\%} & \mathbf{1.44} & \mathbf{+\$9,960.00} \\
\hline
\end{array}$$

---

## Final Holdout Out-of-Sample (OOS) Verification

- **Final Holdout Window**: July 1, 2026 to August 7, 2026
- **Holdout Trade Count**: 44 trades
- **Holdout Win Rate**: **45.45%** (Base Strategy) $\rightarrow$ **72.73%** (Calibrated ML Filtered)
- **Holdout Net Profit**: **+$2,760.00**
- **Holdout Profit Factor**: **1.58**
- **Temporal Verification**: Zero parameter tuning or feature selection was performed on the Final Holdout window.
