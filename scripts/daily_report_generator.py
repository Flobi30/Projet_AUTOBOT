#!/usr/bin/env python3
"""
Daily Report Generator for AUTOBOT Paper Trading Phase 4.

Generates comprehensive daily reports including:
- P&L summary
- Trade statistics
- Win rate analysis
- Risk metrics
- Validation criteria progress

Usage:
    # Generate today's report
    python scripts/daily_report_generator.py
    
    # Generate report for specific date
    python scripts/daily_report_generator.py --date 2026-02-05
    
    # Generate final J7 report
    python scripts/daily_report_generator.py --final
"""

import argparse
import json
import logging
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/daily_report.log')
    ]
)
logger = logging.getLogger(__name__)


class DailyReportGenerator:
    """
    Generates daily and final reports for paper trading sessions.
    
    Reports include:
    - Daily P&L and trade statistics
    - Cumulative performance metrics
    - Validation criteria status
    - Recommendations for optimization
    """
    
    def __init__(
        self,
        log_dir: str = "logs",
        initial_capital: float = 500.0
    ):
        """
        Initialize report generator.
        
        Args:
            log_dir: Directory containing trading logs
            initial_capital: Initial capital amount
        """
        self.log_dir = Path(log_dir)
        self.initial_capital = initial_capital
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"DailyReportGenerator initialized: log_dir={log_dir}")
    
    def _load_trading_log(self, log_date: date) -> Optional[Dict[str, Any]]:
        """Load trading log for a specific date."""
        log_file = self.log_dir / f"papier_trading_{log_date.strftime('%Y%m%d')}.json"
        
        if not log_file.exists():
            logger.warning(f"No trading log found for {log_date}")
            return None
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load trading log: {e}")
            return None
    
    def _load_all_trading_logs(self) -> List[Dict[str, Any]]:
        """Load all available trading logs."""
        logs = []
        
        for log_file in sorted(self.log_dir.glob("papier_trading_*.json")):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs.append(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load {log_file}: {e}")
        
        return logs
    
    def generate_daily_report(self, report_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Generate daily report.
        
        Args:
            report_date: Date to generate report for (default: today)
            
        Returns:
            Report dictionary
        """
        if report_date is None:
            report_date = date.today()
        
        data = self._load_trading_log(report_date)
        
        if data is None:
            return {
                "status": "no_data",
                "date": report_date.isoformat(),
                "message": f"No trading data available for {report_date}",
            }
        
        daily = data.get("daily_metrics", {})
        cumulative = data.get("cumulative_metrics", {})
        validation = data.get("validation_status", {})
        trades = data.get("trades", [])
        
        report = {
            "report_type": "daily",
            "date": report_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "session_id": data.get("session_id", "unknown"),
            
            "summary": {
                "trades_count": daily.get("trades_count", 0),
                "buy_count": daily.get("buy_count", 0),
                "sell_count": daily.get("sell_count", 0),
                "win_count": daily.get("win_count", 0),
                "loss_count": daily.get("loss_count", 0),
                "win_rate": round(daily.get("win_rate", 0.0), 2),
                "total_pnl": round(daily.get("total_pnl", 0.0), 2),
                "net_pnl": round(daily.get("net_pnl", 0.0), 2),
                "total_fees": round(daily.get("total_fees", 0.0), 4),
                "roi_percent": round(daily.get("roi_percent", 0.0), 2),
            },
            
            "capital": {
                "start_balance": round(daily.get("start_balance", self.initial_capital), 2),
                "end_balance": round(daily.get("end_balance", self.initial_capital), 2),
                "daily_change": round(daily.get("net_pnl", 0.0), 2),
                "daily_change_percent": round(daily.get("roi_percent", 0.0), 2),
            },
            
            "trades": {
                "best_trade": round(daily.get("best_trade", 0.0), 2),
                "worst_trade": round(daily.get("worst_trade", 0.0), 2),
                "avg_trade_pnl": round(daily.get("avg_trade_pnl", 0.0), 2),
                "volume_traded": round(daily.get("volume_traded", 0.0), 2),
            },
            
            "cumulative": {
                "total_days": cumulative.get("total_days", 0),
                "total_trades": cumulative.get("total_trades", 0),
                "overall_win_rate": round(cumulative.get("overall_win_rate", 0.0), 2),
                "total_pnl": round(cumulative.get("net_pnl", 0.0), 2),
                "roi_percent": round(cumulative.get("roi_percent", 0.0), 2),
                "max_drawdown": round(cumulative.get("max_drawdown", 0.0), 2),
                "sharpe_ratio": round(cumulative.get("sharpe_ratio", 0.0), 2),
                "profit_factor": round(cumulative.get("profit_factor", 0.0), 2),
            },
            
            "validation": {
                "min_trades_met": validation.get("min_trades_met", False),
                "min_win_rate_met": validation.get("min_win_rate_met", False),
                "max_drawdown_met": validation.get("max_drawdown_met", True),
                "min_profit_factor_met": validation.get("min_profit_factor_met", False),
                "overall_status": validation.get("overall_status", "PENDING"),
            },
            
            "recent_trades": trades[-10:] if trades else [],
        }
        
        return report
    
    def generate_final_report(self) -> Dict[str, Any]:
        """
        Generate final J7 report with recommendations.
        
        Returns:
            Final report dictionary
        """
        all_logs = self._load_all_trading_logs()
        
        if not all_logs:
            return {
                "status": "no_data",
                "message": "No trading data available for final report",
            }
        
        latest = all_logs[-1]
        cumulative = latest.get("cumulative_metrics", {})
        validation = latest.get("validation_status", {})
        
        daily_pnls = []
        daily_trades = []
        
        for log in all_logs:
            daily = log.get("daily_metrics", {})
            daily_pnls.append(daily.get("net_pnl", 0.0))
            daily_trades.append(daily.get("trades_count", 0))
        
        avg_daily_pnl = sum(daily_pnls) / len(daily_pnls) if daily_pnls else 0.0
        avg_daily_trades = sum(daily_trades) / len(daily_trades) if daily_trades else 0.0
        
        total_trades = cumulative.get("total_trades", 0)
        win_rate = cumulative.get("overall_win_rate", 0.0)
        max_drawdown = cumulative.get("max_drawdown", 0.0)
        profit_factor = cumulative.get("profit_factor", 0.0)
        sharpe_ratio = cumulative.get("sharpe_ratio", 0.0)
        
        criteria_results = {
            "min_trades": {
                "required": 50,
                "actual": total_trades,
                "met": total_trades >= 50,
            },
            "win_rate": {
                "required": 50.0,
                "actual": round(win_rate, 2),
                "met": win_rate >= 50.0,
            },
            "max_drawdown": {
                "required": 20.0,
                "actual": round(max_drawdown, 2),
                "met": max_drawdown <= 20.0,
            },
            "profit_factor": {
                "required": 1.2,
                "actual": round(profit_factor, 2),
                "met": profit_factor >= 1.2,
            },
        }
        
        criteria_met = sum(1 for c in criteria_results.values() if c["met"])
        total_criteria = len(criteria_results)
        
        if criteria_met == total_criteria:
            overall_status = "GO"
            recommendation = "Tous les criteres sont valides. AUTOBOT est pret pour le trading reel avec 500 EUR."
        elif criteria_met >= total_criteria - 1:
            overall_status = "REVIEW"
            recommendation = f"{criteria_met}/{total_criteria} criteres valides. Revision recommandee avant passage en reel."
        else:
            overall_status = "NO-GO"
            recommendation = f"Seulement {criteria_met}/{total_criteria} criteres valides. Continuer le papier trading."
        
        optimizations = []
        
        if win_rate < 50.0:
            optimizations.append({
                "area": "Win Rate",
                "current": f"{win_rate:.1f}%",
                "target": "50%+",
                "suggestion": "Ajuster les niveaux de grid pour capturer plus de mouvements profitables",
            })
        
        if max_drawdown > 15.0:
            optimizations.append({
                "area": "Drawdown",
                "current": f"{max_drawdown:.1f}%",
                "target": "<15%",
                "suggestion": "Reduire la taille des positions ou elargir la plage de grid",
            })
        
        if profit_factor < 1.2:
            optimizations.append({
                "area": "Profit Factor",
                "current": f"{profit_factor:.2f}",
                "target": "1.2+",
                "suggestion": "Augmenter le profit par niveau ou reduire les frais",
            })
        
        if avg_daily_trades < 5:
            optimizations.append({
                "area": "Frequence de Trading",
                "current": f"{avg_daily_trades:.1f} trades/jour",
                "target": "5+ trades/jour",
                "suggestion": "Resserrer la plage de grid ou augmenter le nombre de niveaux",
            })
        
        report = {
            "report_type": "final_j7",
            "generated_at": datetime.utcnow().isoformat(),
            "session_id": latest.get("session_id", "unknown"),
            "duration_days": len(all_logs),
            
            "performance_summary": {
                "initial_capital": self.initial_capital,
                "final_capital": round(cumulative.get("current_capital", self.initial_capital), 2),
                "total_pnl": round(cumulative.get("net_pnl", 0.0), 2),
                "roi_percent": round(cumulative.get("roi_percent", 0.0), 2),
                "total_trades": total_trades,
                "win_rate": round(win_rate, 2),
                "max_drawdown": round(max_drawdown, 2),
                "sharpe_ratio": round(sharpe_ratio, 2),
                "profit_factor": round(profit_factor, 2),
            },
            
            "daily_statistics": {
                "avg_daily_pnl": round(avg_daily_pnl, 2),
                "avg_daily_trades": round(avg_daily_trades, 1),
                "best_day_pnl": round(cumulative.get("best_day_pnl", 0.0), 2),
                "worst_day_pnl": round(cumulative.get("worst_day_pnl", 0.0), 2),
            },
            
            "validation_criteria": criteria_results,
            
            "decision": {
                "overall_status": overall_status,
                "criteria_met": f"{criteria_met}/{total_criteria}",
                "recommendation": recommendation,
            },
            
            "optimizations": optimizations,
            
            "next_steps": self._generate_next_steps(overall_status, optimizations),
        }
        
        return report
    
    def _generate_next_steps(
        self,
        status: str,
        optimizations: List[Dict]
    ) -> List[str]:
        """Generate recommended next steps based on results."""
        steps = []
        
        if status == "GO":
            steps = [
                "1. Preparer le compte Binance reel avec 500 EUR",
                "2. Configurer les cles API de production",
                "3. Lancer AUTOBOT en mode reel avec surveillance accrue",
                "4. Monitorer les 24 premieres heures de trading reel",
            ]
        elif status == "REVIEW":
            steps = [
                "1. Analyser les trades perdants pour identifier les patterns",
                "2. Ajuster les parametres de grid selon les optimisations suggerees",
                "3. Relancer le papier trading pour 3 jours supplementaires",
                "4. Re-evaluer les criteres de validation",
            ]
        else:
            steps = [
                "1. Revoir la strategie de grid trading",
                "2. Implementer les optimisations suggerees",
                "3. Tester avec des parametres plus conservateurs",
                "4. Continuer le papier trading jusqu'a validation",
            ]
        
        return steps
    
    def save_report(self, report: Dict[str, Any], filename: str) -> Path:
        """
        Save report to file.
        
        Args:
            report: Report dictionary
            filename: Output filename
            
        Returns:
            Path to saved file
        """
        output_path = self.log_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Report saved: {output_path}")
        return output_path
    
    def save_markdown_report(self, report: Dict[str, Any], filename: str) -> Path:
        """
        Save report as Markdown file.
        
        Args:
            report: Report dictionary
            filename: Output filename
            
        Returns:
            Path to saved file
        """
        output_path = self.log_dir / filename
        
        md_content = self._generate_markdown(report)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Markdown report saved: {output_path}")
        return output_path
    
    def _generate_markdown(self, report: Dict[str, Any]) -> str:
        """Generate Markdown content from report."""
        report_type = report.get("report_type", "unknown")
        
        if report_type == "final_j7":
            return self._generate_final_markdown(report)
        else:
            return self._generate_daily_markdown(report)
    
    def _generate_daily_markdown(self, report: Dict[str, Any]) -> str:
        """Generate daily report Markdown."""
        summary = report.get("summary", {})
        capital = report.get("capital", {})
        cumulative = report.get("cumulative", {})
        
        md = f"""# Rapport Quotidien - Paper Trading Phase 4

**Date:** {report.get('date', 'N/A')}  
**Session:** {report.get('session_id', 'N/A')}  
**Genere le:** {report.get('generated_at', 'N/A')}

---

## Resume du Jour

| Metrique | Valeur |
|----------|--------|
| Trades | {summary.get('trades_count', 0)} |
| Achats | {summary.get('buy_count', 0)} |
| Ventes | {summary.get('sell_count', 0)} |
| Gagnants | {summary.get('win_count', 0)} |
| Perdants | {summary.get('loss_count', 0)} |
| Win Rate | {summary.get('win_rate', 0)}% |
| P&L Net | {summary.get('net_pnl', 0):.2f} EUR |
| ROI | {summary.get('roi_percent', 0):.2f}% |

## Capital

| Metrique | Valeur |
|----------|--------|
| Debut de journee | {capital.get('start_balance', 0):.2f} EUR |
| Fin de journee | {capital.get('end_balance', 0):.2f} EUR |
| Variation | {capital.get('daily_change', 0):.2f} EUR ({capital.get('daily_change_percent', 0):.2f}%) |

## Performance Cumulative

| Metrique | Valeur |
|----------|--------|
| Jours de trading | {cumulative.get('total_days', 0)} |
| Total trades | {cumulative.get('total_trades', 0)} |
| Win Rate global | {cumulative.get('overall_win_rate', 0):.2f}% |
| P&L Total | {cumulative.get('total_pnl', 0):.2f} EUR |
| ROI Total | {cumulative.get('roi_percent', 0):.2f}% |
| Max Drawdown | {cumulative.get('max_drawdown', 0):.2f}% |
| Sharpe Ratio | {cumulative.get('sharpe_ratio', 0):.2f} |
| Profit Factor | {cumulative.get('profit_factor', 0):.2f} |

---

*Rapport genere automatiquement par AUTOBOT*
"""
        return md
    
    def _generate_final_markdown(self, report: Dict[str, Any]) -> str:
        """Generate final J7 report Markdown."""
        perf = report.get("performance_summary", {})
        daily = report.get("daily_statistics", {})
        criteria = report.get("validation_criteria", {})
        decision = report.get("decision", {})
        optimizations = report.get("optimizations", [])
        next_steps = report.get("next_steps", [])
        
        criteria_table = ""
        for name, data in criteria.items():
            status = "OK" if data.get("met") else "NON"
            criteria_table += f"| {name} | {data.get('required')} | {data.get('actual')} | {status} |\n"
        
        opt_section = ""
        if optimizations:
            for opt in optimizations:
                opt_section += f"\n### {opt.get('area')}\n"
                opt_section += f"- **Actuel:** {opt.get('current')}\n"
                opt_section += f"- **Cible:** {opt.get('target')}\n"
                opt_section += f"- **Suggestion:** {opt.get('suggestion')}\n"
        else:
            opt_section = "\nAucune optimisation requise.\n"
        
        steps_section = "\n".join(next_steps)
        
        md = f"""# Rapport Final J7 - Paper Trading Phase 4

**Session:** {report.get('session_id', 'N/A')}  
**Duree:** {report.get('duration_days', 0)} jours  
**Genere le:** {report.get('generated_at', 'N/A')}

---

## Decision Finale

### Statut: **{decision.get('overall_status', 'PENDING')}**

{decision.get('recommendation', '')}

Criteres valides: **{decision.get('criteria_met', '0/0')}**

---

## Performance Globale

| Metrique | Valeur |
|----------|--------|
| Capital Initial | {perf.get('initial_capital', 0):.2f} EUR |
| Capital Final | {perf.get('final_capital', 0):.2f} EUR |
| P&L Total | {perf.get('total_pnl', 0):.2f} EUR |
| ROI | {perf.get('roi_percent', 0):.2f}% |
| Total Trades | {perf.get('total_trades', 0)} |
| Win Rate | {perf.get('win_rate', 0):.2f}% |
| Max Drawdown | {perf.get('max_drawdown', 0):.2f}% |
| Sharpe Ratio | {perf.get('sharpe_ratio', 0):.2f} |
| Profit Factor | {perf.get('profit_factor', 0):.2f} |

## Statistiques Quotidiennes

| Metrique | Valeur |
|----------|--------|
| P&L Moyen/Jour | {daily.get('avg_daily_pnl', 0):.2f} EUR |
| Trades Moyens/Jour | {daily.get('avg_daily_trades', 0):.1f} |
| Meilleur Jour | {daily.get('best_day_pnl', 0):.2f} EUR |
| Pire Jour | {daily.get('worst_day_pnl', 0):.2f} EUR |

## Criteres de Validation

| Critere | Requis | Actuel | Statut |
|---------|--------|--------|--------|
{criteria_table}

## Recommandations d'Optimisation
{opt_section}

## Prochaines Etapes

{steps_section}

---

*Rapport genere automatiquement par AUTOBOT Paper Trading Phase 4*
"""
        return md


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AUTOBOT Paper Trading Daily Report Generator"
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Date to generate report for (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--final',
        action='store_true',
        help='Generate final J7 report'
    )
    parser.add_argument(
        '--markdown',
        action='store_true',
        help='Also generate Markdown version'
    )
    parser.add_argument(
        '--log-dir',
        type=str,
        default='logs',
        help='Directory containing trading logs'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output filename (without extension)'
    )
    
    args = parser.parse_args()
    
    generator = DailyReportGenerator(log_dir=args.log_dir)
    
    if args.final:
        report = generator.generate_final_report()
        filename = args.output or f"rapport_final_j7_{date.today().strftime('%Y%m%d')}"
    else:
        report_date = None
        if args.date:
            report_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        
        report = generator.generate_daily_report(report_date)
        filename = args.output or f"rapport_quotidien_{(report_date or date.today()).strftime('%Y%m%d')}"
    
    json_path = generator.save_report(report, f"{filename}.json")
    print(f"JSON report saved: {json_path}")
    
    if args.markdown:
        md_path = generator.save_markdown_report(report, f"{filename}.md")
        print(f"Markdown report saved: {md_path}")
    
    print("\n" + "="*60)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print("="*60)


if __name__ == "__main__":
    main()
