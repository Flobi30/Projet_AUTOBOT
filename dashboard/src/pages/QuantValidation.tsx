import React, { useEffect, useState } from 'react';
import { Activity, BarChart3, BrainCircuit, ShieldCheck, TrendingUp } from 'lucide-react';
import MetricCard from '../components/ui/MetricCard';
import { apiFetch } from '../api/client';

type VolatilityRow = {
  symbol: string;
  state: string;
  sample_count: number;
  forecast_vol_bps: number;
  ewma_vol_bps: number;
  trend_bps: number;
  confidence: number;
  reason: string;
};

type BacktestQuality = {
  status: string;
  recommendation: string;
  sample: {
    executions_count: number;
    realized_trade_count: number;
    min_trades: number;
    sources: string[];
  };
  metrics: {
    trade_count: number;
    net_pnl_eur: number;
    gross_profit_eur: number;
    gross_loss_eur: number;
    profit_factor: number;
    win_rate: number;
    avg_return_pct: number;
    vol_return_pct: number;
    sharpe: number;
    max_drawdown_eur: number;
    max_drawdown_pct: number;
  };
  pbo: {
    status: string;
    probability: number | null;
    reason: string;
  };
  dsr: {
    status: string;
    probability: number | null;
    deflated_sharpe_z: number | null;
    reason: string;
  };
  by_symbol: Array<{
    symbol: string;
    trade_count: number;
    net_pnl_eur: number;
    win_rate: number;
    avg_pnl_eur: number;
  }>;
};

type QuantValidationResponse = {
  timestamp: string;
  mode: string;
  paper_mode: boolean;
  live_shadow_policy: {
    paper_shadow_continues_in_live: boolean;
    shadow_trading_enabled: boolean;
    live_execution_enabled: boolean;
    live_selection_enabled: boolean;
    live_confirmation: boolean;
    deployment_stage: string;
    message: string;
  };
  volatility: {
    symbols: VolatilityRow[];
  };
  backtest_quality: BacktestQuality;
  runtime?: {
    running: boolean;
    websocket_connected: boolean;
    instance_count: number;
  };
  capital?: {
    capital_base: number;
    source?: string;
    source_status?: string;
  };
};

const formatBps = (value?: number) =>
  typeof value === 'number' ? `${value.toFixed(1)} bps` : 'En attente';

const formatPct = (value?: number | null, scale = 100) =>
  typeof value === 'number' ? `${(value * scale).toFixed(1)}%` : 'En attente';

const formatCurrency = (value?: number) =>
  typeof value === 'number'
    ? value.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })
    : 'En attente';

const stateClass = (state?: string) => {
  if (state === 'candidate' || state === 'acceptable' || state === 'normal') return 'text-emerald-400';
  if (state === 'unsafe' || state === 'high_overfit_risk' || state === 'extreme') return 'text-red-400';
  if (state === 'weak' || state === 'caution' || state === 'high' || state === 'rising') return 'text-amber-400';
  return 'text-gray-300';
};

const QuantValidation: React.FC = () => {
  const [data, setData] = useState<QuantValidationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await apiFetch('/api/quant/validation');
        if (!response.ok) {
          setError(`API quant indisponible: ${response.status}`);
          setIsLoading(false);
          return;
        }
        setData(await response.json());
        setError(null);
      } catch {
        setError('Erreur lors de la recuperation de la validation quant');
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

  if (isLoading) {
    return (
      <div className="p-8 bg-gray-900 min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center">
          <div className="w-12 h-12 border-4 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin" />
          <span className="mt-4 text-emerald-400">Chargement...</span>
        </div>
      </div>
    );
  }

  const quality = data?.backtest_quality;
  const policy = data?.live_shadow_policy;
  const volatilityRows = data?.volatility.symbols ?? [];

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex items-center space-x-3 mb-3">
          <BrainCircuit className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400" />
          <h1 className="text-2xl lg:text-4xl font-bold text-white">Validation Quant</h1>
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">
          Controle paper/shadow pour verifier la robustesse avant tout live.
        </p>
      </div>

      {error ? (
        <div className="mb-6 border border-red-500/30 bg-red-500/10 rounded-xl p-4 text-red-200">
          {error}
        </div>
      ) : null}

      {policy ? (
        <div className="mb-6 border border-emerald-500/30 bg-emerald-500/10 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-emerald-300 mt-0.5" />
            <div>
              <div className="text-white font-semibold">
                Paper/shadow en continu: {policy.paper_shadow_continues_in_live ? 'actif' : 'desactive'}
              </div>
              <div className="text-sm text-emerald-100/80 mt-1">
                Live execution: {policy.live_execution_enabled ? 'actif' : 'bloque'} | Stage: {policy.deployment_stage}
              </div>
              <div className="text-sm text-gray-300 mt-1">{policy.message}</div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <MetricCard title="Mode" value={data?.paper_mode ? 'PAPER' : (data?.mode ?? 'Inconnu').toUpperCase()} icon={<Activity className="w-5 h-5" />} />
        <MetricCard title="Capital observe" value={formatCurrency(data?.capital?.capital_base)} icon={<TrendingUp className="w-5 h-5" />} />
        <MetricCard title="Trades clotures" value={`${quality?.sample.realized_trade_count ?? 0}/${quality?.sample.min_trades ?? 0}`} icon={<BarChart3 className="w-5 h-5" />} />
        <MetricCard title="PBO / DSR" value={`${formatPct(quality?.pbo.probability, 100)} / ${formatPct(quality?.dsr.probability, 100)}`} icon={<ShieldCheck className="w-5 h-5" />} />
      </div>

      <div className="grid grid-cols-1 2xl:grid-cols-2 gap-6 mb-8">
        <section className="bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="text-xl font-bold text-white">Qualite backtest paper</h2>
            <span className={`text-sm font-semibold ${stateClass(quality?.status)}`}>
              {quality?.status ?? 'indisponible'}
            </span>
          </div>
          <p className="text-sm text-gray-300 mb-5">
            {quality?.recommendation ?? 'En attente de donnees paper.'}
          </p>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">PnL net</div>
              <div className="text-white font-semibold">{formatCurrency(quality?.metrics.net_pnl_eur)}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Profit factor</div>
              <div className="text-white font-semibold">{quality?.metrics.profit_factor?.toFixed(2) ?? 'En attente'}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Win rate</div>
              <div className="text-white font-semibold">{formatPct(quality?.metrics.win_rate, 100)}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Sharpe</div>
              <div className="text-white font-semibold">{quality?.metrics.sharpe?.toFixed(2) ?? 'En attente'}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Drawdown max</div>
              <div className="text-white font-semibold">{quality?.metrics.max_drawdown_pct?.toFixed(2) ?? '0.00'}%</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Sources</div>
              <div className="text-white font-semibold">{quality?.sample.sources?.join(', ') || 'Aucune'}</div>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div className="border border-gray-700 rounded-lg p-3">
              <div className="flex justify-between">
                <span className="text-gray-400">PBO</span>
                <span className={stateClass(quality?.pbo.status)}>{quality?.pbo.status ?? 'indisponible'}</span>
              </div>
              <div className="text-white font-semibold mt-1">{formatPct(quality?.pbo.probability, 100)}</div>
              <div className="text-xs text-gray-500 mt-1">{quality?.pbo.reason ?? 'En attente'}</div>
            </div>
            <div className="border border-gray-700 rounded-lg p-3">
              <div className="flex justify-between">
                <span className="text-gray-400">DSR</span>
                <span className={stateClass(quality?.dsr.status)}>{quality?.dsr.status ?? 'indisponible'}</span>
              </div>
              <div className="text-white font-semibold mt-1">{formatPct(quality?.dsr.probability, 100)}</div>
              <div className="text-xs text-gray-500 mt-1">{quality?.dsr.reason ?? 'En attente'}</div>
            </div>
          </div>
        </section>

        <section className="bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="text-xl font-bold text-white">Volatilite par paire</h2>
            <span className="text-sm text-gray-400">{volatilityRows.length} paires</span>
          </div>
          <div className="space-y-3">
            {volatilityRows.slice(0, 10).map((row) => (
              <div key={row.symbol} className="border border-gray-700 rounded-lg p-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-white font-semibold">{row.symbol}</span>
                  <span className={`text-sm font-semibold ${stateClass(row.state)}`}>{row.state}</span>
                </div>
                <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  <span className="text-gray-400">Forecast <span className="text-white">{formatBps(row.forecast_vol_bps)}</span></span>
                  <span className="text-gray-400">EWMA <span className="text-white">{formatBps(row.ewma_vol_bps)}</span></span>
                  <span className="text-gray-400">Trend <span className={row.trend_bps >= 0 ? 'text-emerald-400' : 'text-red-400'}>{formatBps(row.trend_bps)}</span></span>
                  <span className="text-gray-400">Samples <span className="text-white">{row.sample_count}</span></span>
                </div>
                <div className="text-xs text-gray-500 mt-2">{row.reason}</div>
              </div>
            ))}
            {volatilityRows.length === 0 ? (
              <div className="text-gray-500 text-sm text-center py-8">
                Aucun historique de prix exploitable pour le moment.
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <section className="bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
        <h2 className="text-xl font-bold text-white mb-4">Resultats par paire</h2>
        {quality?.by_symbol?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-gray-400">
                <tr className="border-b border-gray-700">
                  <th className="text-left py-2">Paire</th>
                  <th className="text-right py-2">Trades</th>
                  <th className="text-right py-2">PnL</th>
                  <th className="text-right py-2">Win rate</th>
                  <th className="text-right py-2">PnL moyen</th>
                </tr>
              </thead>
              <tbody>
                {quality.by_symbol.map((row) => (
                  <tr key={row.symbol} className="border-b border-gray-700/50">
                    <td className="py-2 text-white">{row.symbol}</td>
                    <td className="py-2 text-right text-gray-300">{row.trade_count}</td>
                    <td className={`py-2 text-right ${row.net_pnl_eur >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(row.net_pnl_eur)}</td>
                    <td className="py-2 text-right text-gray-300">{formatPct(row.win_rate, 100)}</td>
                    <td className="py-2 text-right text-gray-300">{formatCurrency(row.avg_pnl_eur)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-gray-500 text-sm">
            Aucun trade cloture exploitable. AUTOBOT peut etre actif sans avoir encore assez de ventes/fermetures pour juger le backtest.
          </div>
        )}
      </section>
    </div>
  );
};

export default QuantValidation;
