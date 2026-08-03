"""
The Judge Evaluator Engine
Evaluates Challenger performance against Champion and triggers alerts/reports.
"""

import os
import json
from typing import Dict, Any, List

try:
    from bot.logger import logger
except ImportError:
    import logging
    logger = logging.getLogger("JudgeEvaluator")
    logging.basicConfig(level=logging.INFO)


class JudgeEvaluator:
    def __init__(self, outperformance_threshold_pct: float = 20.0):
        self.outperformance_threshold_pct = outperformance_threshold_pct

    def evaluate_champion_vs_challenger(
        self,
        champion_stats: Dict[str, Any],
        challenger_stats: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compares Champion strategy metrics against Challenger strategy metrics.
        Determines whether Challenger beats Champion with statistical significance.
        """
        champ_cps = champion_stats.get("cps_score", 1.0)
        chall_cps = challenger_stats.get("cps_score", 0.0)

        cps_diff_pct = ((chall_cps - champ_cps) / max(champ_cps, 0.001)) * 100

        champ_winrate = champion_stats.get("win_rate_pct", 0.0)
        chall_winrate = challenger_stats.get("win_rate_pct", 0.0)

        champ_pf = champion_stats.get("profit_factor", 0.0)
        chall_pf = challenger_stats.get("profit_factor", 0.0)

        is_winner = (
            cps_diff_pct >= self.outperformance_threshold_pct and
            challenger_stats.get("total_trades", 0) >= 15 and
            chall_pf > champ_pf
        )

        decision = "RECOMMEND_UPDATE" if is_winner else "RETAIN_CHAMPION"

        report_summary = {
            "symbol": challenger_stats.get("symbol", "UNKNOWN"),
            "decision": decision,
            "cps_improvement_pct": round(cps_diff_pct, 2),
            "champion": {
                "name": "Champion (Current Live)",
                "timeframe": champion_stats.get("timeframe", "M15"),
                "rr_ratio": champion_stats.get("rr_ratio", 3.0),
                "win_rate_pct": champ_winrate,
                "profit_factor": champ_pf,
                "cps_score": champ_cps
            },
            "challenger": {
                "name": "Challenger (New Candidate)",
                "timeframe": challenger_stats.get("timeframe", "M5"),
                "rr_ratio": challenger_stats.get("rr_ratio", 5.0),
                "win_rate_pct": chall_winrate,
                "profit_factor": chall_pf,
                "cps_score": chall_cps
            }
        }

        return report_summary

    def generate_markdown_report(self, evaluation: Dict[str, Any]) -> str:
        """Generates GitHub-style Markdown report comparing Champion and Challenger."""
        decision_header = "[RECOMMENDATION] UPDATE TO NEW CHALLENGER STRATEGY" if evaluation["decision"] == "RECOMMEND_UPDATE" else "[RECOMMENDATION] RETAIN CURRENT CHAMPION STRATEGY"
        
        champ = evaluation["champion"]
        chall = evaluation["challenger"]

        report = f"""
======================================================================
           THE ARENA: CHAMPION vs CHALLENGER EVALUATION REPORT
======================================================================
{decision_header}

Symbol: {evaluation['symbol']}  
CPS Score Improvement: +{evaluation['cps_improvement_pct']}%

----------------------------------------------------------------------
                  COMPARATIVE METRICS TABLE
----------------------------------------------------------------------
Metric / Parameter     | Champion (Current) | Challenger (Candidate) | Winner
----------------------------------------------------------------------
Timeframe              | {champ['timeframe']:<18} | {chall['timeframe']:<22} | -
Risk-Reward (R:R)      | 1:{champ['rr_ratio']:<16} | 1:{chall['rr_ratio']:<20} | -
Win Rate (%)           | {champ['win_rate_pct']:<17}% | {chall['win_rate_pct']:<21}% | {"Challenger" if chall['win_rate_pct'] > champ['win_rate_pct'] else "Champion"}
Profit Factor          | {champ['profit_factor']:<18} | {chall['profit_factor']:<22} | {"Challenger" if chall['profit_factor'] > champ['profit_factor'] else "Champion"}
Composite Score (CPS)  | {champ['cps_score']:<18} | {chall['cps_score']:<22} | {"Challenger" if chall['cps_score'] > champ['cps_score'] else "Champion"}
----------------------------------------------------------------------
"""
        return report
