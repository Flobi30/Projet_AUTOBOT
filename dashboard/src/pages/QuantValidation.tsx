import React, { useEffect, useState } from 'react';
import { Activity, BarChart3, BrainCircuit, ShieldCheck, SlidersHorizontal, TrendingUp } from 'lucide-react';
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

type SetupAuditRow = {
  symbol: string;
  strategy: string;
  closed_trades: number;
  net_pnl_eur: number;
  profit_factor: number | null;
  win_rate: number;
  verdict: string;
  recommended_action: string;
  root_causes: string[];
  opportunity_score?: number | null;
  optimizer_status?: string | null;
  optimizer_action?: string | null;
  recommended_variant?: string | null;
  recommended_variant_score?: number | null;
  shadow_best_variant?: string | null;
  shadow_best_score?: number | null;
  shadow_net_pnl_eur?: number | null;
  shadow_closed_trades?: number | null;
};

type SetupAuditResponse = {
  global_verdict: string;
  live_promotion_allowed: boolean;
  global: {
    closed_trades: number;
    net_pnl_eur: number;
    profit_factor: number | null;
    win_rate: number;
    source?: string;
  };
  thresholds: {
    min_closed_trades: number;
    candidate_profit_factor: number;
    candidate_min_net_pnl_eur: number;
  };
  setups: SetupAuditRow[];
  message: string;
};

type SetupOptimizerVariant = {
  name: string;
  score: number;
  status: string;
  reason: string;
  estimated_grid_gross_edge_bps: number;
  estimated_net_after_cost_bps: number | null;
  grid_config: {
    range_percent?: number;
    num_levels?: number;
    max_capital_per_level?: number;
    entry_touch_bps?: number;
    estimated_sell_threshold_pct?: number;
  };
  shadow_metrics?: {
    evidence_source?: string;
    status?: string;
    score?: number;
    net_pnl_eur?: number;
    closed_trades?: number;
    [key: string]: unknown;
  };
};

type SetupOptimizerRow = {
  symbol: string;
  status: string;
  recommended_action: string;
  selected_variant: SetupOptimizerVariant | null;
  evidence: {
    closed_trades: number;
    net_pnl_eur: number;
    profit_factor: number | null;
    health_status: string;
    opportunity_score: number;
    opportunity_reason?: string;
  };
  current_context: {
    regime?: string;
    profile_source?: string;
    base_range_pct?: number;
    base_num_levels?: number;
  };
};

type SetupOptimizerResponse = {
  enabled: boolean;
  live_promotion_allowed: boolean;
  applies_to_execution: boolean;
  summary: {
    symbols: number;
    candidate_setups: number;
    learning_setups: number;
    weak_or_adjust_setups: number;
  };
  setups: SetupOptimizerRow[];
  setup_shadow?: {
    enabled: boolean;
    paper_only: boolean;
    live_promotion_allowed: boolean;
    summary: {
      symbols: number;
      variant_states: number;
      open_shadow_positions: number;
      closed_shadow_trades: number;
      net_shadow_pnl_eur: number;
      candidate_symbols: number;
    };
  };
  message: string;
};

type TrendShadowVariant = {
  variant: string;
  status: string;
  score: number;
  net_pnl_eur: number;
  realized_pnl_eur: number;
  profit_factor: number | null;
  win_rate: number;
  opened_trades: number;
  closed_trades: number;
  open_positions: number;
  sample_count: number;
  last_decision?: {
    status?: string;
    reason?: string;
  };
};

type TrendShadowResponse = {
  enabled: boolean;
  paper_only: boolean;
  live_promotion_allowed: boolean;
  summary: {
    symbols: number;
    variant_states: number;
    open_shadow_positions: number;
    closed_shadow_trades: number;
    net_shadow_pnl_eur: number;
    candidate_symbols: number;
  };
  symbols: Array<{
    symbol: string;
    engine: string;
    best_variant: TrendShadowVariant | null;
    variants: TrendShadowVariant[];
  }>;
  message: string;
};

const formatBps = (value?: number) =>
  typeof value === 'number' ? `${value.toFixed(1)} bps` : 'En attente';

const formatPct = (value?: number | null, scale = 100) =>
  typeof value === 'number' ? `${(value * scale).toFixed(1)}%` : 'En attente';

const formatCurrency = (value?: number) =>
  typeof value === 'number'
    ? value.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })
    : 'En attente';

const formatClosedTrades = (quality?: BacktestQuality) =>
  `${quality?.sample.realized_trade_count ?? 0}/${quality?.sample.min_trades ?? 0}`;

const qualityReason = (
  kind: 'pbo' | 'dsr',
  reason: string | undefined,
  quality?: BacktestQuality
) => {
  const closed = quality?.sample.realized_trade_count ?? 0;
  const required = quality?.sample.min_trades ?? 0;
  if (!reason || reason === 'not_enough_realized_trades') {
    return `En attente: ${closed}/${required} trades paper clotures.`;
  }
  if (kind === 'pbo') return reason;
  return reason;
};

const stateClass = (state?: string) => {
  if (state === 'candidate' || state === 'acceptable' || state === 'normal' || state === 'paper_review_candidate' || state === 'paper_candidate_needs_review') return 'text-emerald-400';
  if (state === 'unsafe' || state === 'high_overfit_risk' || state === 'extreme') return 'text-red-400';
  if (state === 'weak' || state === 'caution' || state === 'high' || state === 'rising' || state === 'not_validated' || state === 'watch' || state === 'adjust' || state === 'pause_current' || state === 'learning') return 'text-amber-400';
  return 'text-gray-300';
};

const QuantValidation: React.FC = () => {
  const [data, setData] = useState<QuantValidationResponse | null>(null);
  const [setupAudit, setSetupAudit] = useState<SetupAuditResponse | null>(null);
  const [setupOptimizer, setSetupOptimizer] = useState<SetupOptimizerResponse | null>(null);
  const [trendShadow, setTrendShadow] = useState<TrendShadowResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [response, setupResponse, optimizerResponse, trendResponse] = await Promise.all([
          apiFetch('/api/quant/validation'),
          apiFetch('/api/performance/setup-audit'),
          apiFetch('/api/setup-optimizer'),
          apiFetch('/api/trend-shadow'),
        ]);
        if (!response.ok) {
          setError(`API quant indisponible: ${response.status}`);
          setIsLoading(false);
          return;
        }
        setData(await response.json());
        setSetupAudit(setupResponse.ok ? await setupResponse.json() : null);
        setSetupOptimizer(optimizerResponse.ok ? await optimizerResponse.json() : null);
        setTrendShadow(trendResponse.ok ? await trendResponse.json() : null);
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
  const setupRows = setupAudit?.setups ?? [];
  const optimizerRows = setupOptimizer?.setups ?? [];
  const shadowSummary = setupOptimizer?.setup_shadow?.summary;
  const trendSummary = trendShadow?.summary;
  const trendRows = trendShadow?.symbols ?? [];

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
        <MetricCard title="Trades paper clotures" value={formatClosedTrades(quality)} change="minimum validation" icon={<BarChart3 className="w-5 h-5" />} />
        <MetricCard title="PBO / DSR" value={`${formatPct(quality?.pbo.probability, 100)} / ${formatPct(quality?.dsr.probability, 100)}`} icon={<ShieldCheck className="w-5 h-5" />} />
      </div>

      <div className="mb-6 border border-blue-500/25 bg-blue-500/10 rounded-xl p-4 text-sm text-blue-100/90">
        <strong className="text-white">Lecture rapide:</strong> ce panneau valide le paper/shadow. PBO et DSR restent en attente tant que le bot n'a pas assez de trades paper termines; ils ne declenchent pas le live automatiquement.
      </div>

      {setupAudit ? (
        <section className="mb-8 bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <h2 className="text-xl font-bold text-white">Audit des setups</h2>
              <p className="text-sm text-gray-400 mt-1">{setupAudit.message}</p>
            </div>
            <span className={`text-sm font-semibold ${stateClass(setupAudit.global_verdict)}`}>
              {setupAudit.global_verdict}
            </span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm mb-4">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">PnL setup global</div>
              <div className={setupAudit.global.net_pnl_eur >= 0 ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold'}>{formatCurrency(setupAudit.global.net_pnl_eur)}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">PF global</div>
              <div className="text-white font-semibold">{setupAudit.global.profit_factor?.toFixed(2) ?? 'En attente'}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Clotures</div>
              <div className="text-white font-semibold">{setupAudit.global.closed_trades}/{setupAudit.thresholds.min_closed_trades}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Live auto</div>
              <div className="text-white font-semibold">{setupAudit.live_promotion_allowed ? 'Autorise' : 'Bloque'}</div>
            </div>
          </div>
          {setupRows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2">Setup</th>
                    <th className="text-right py-2">Trades</th>
                    <th className="text-right py-2">PnL</th>
                    <th className="text-right py-2">PF</th>
                    <th className="text-right py-2">Score</th>
                    <th className="text-left py-2 pl-4">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {setupRows.slice(0, 12).map((row) => (
                    <tr key={`${row.symbol}-${row.strategy}`} className="border-b border-gray-700/50">
                      <td className="py-2 text-white">{row.symbol} <span className="text-gray-500">/ {row.strategy}</span></td>
                      <td className="py-2 text-right text-gray-300">{row.closed_trades}</td>
                      <td className={`py-2 text-right ${row.net_pnl_eur >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(row.net_pnl_eur)}</td>
                      <td className="py-2 text-right text-gray-300">{row.profit_factor?.toFixed(2) ?? 'En attente'}</td>
                      <td className="py-2 text-right text-gray-300">{row.opportunity_score?.toFixed(1) ?? 'En attente'}</td>
                      <td className="py-2 pl-4">
                        <div className={`font-semibold ${stateClass(row.verdict)}`}>{row.verdict}</div>
                        <div className="text-xs text-gray-500">
                          {row.shadow_best_variant
                            ? `Shadow: ${row.shadow_best_variant} (${row.shadow_best_score?.toFixed(1) ?? 'score ?'}, ${formatCurrency(row.shadow_net_pnl_eur ?? undefined)})`
                            : row.recommended_variant ? `${row.recommended_variant} (${row.recommended_variant_score?.toFixed(1) ?? 'score ?'})` : row.root_causes.slice(0, 2).join(', ') || row.recommended_action}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Aucun setup auditable pour le moment.</div>
          )}
        </section>
      ) : null}

      {setupOptimizer ? (
        <section className="mb-8 bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="flex items-start gap-3">
              <SlidersHorizontal className="w-5 h-5 text-emerald-300 mt-1" />
              <div>
                <h2 className="text-xl font-bold text-white">Optimiseur adaptatif paper</h2>
                <p className="text-sm text-gray-400 mt-1">{setupOptimizer.message}</p>
              </div>
            </div>
            <span className="text-sm text-gray-400">{setupOptimizer.summary.symbols} setups</span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm mb-4">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Candidats paper</div>
              <div className="text-emerald-400 font-semibold">{setupOptimizer.summary.candidate_setups}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">En apprentissage</div>
              <div className="text-white font-semibold">{setupOptimizer.summary.learning_setups}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">A ajuster</div>
              <div className="text-amber-400 font-semibold">{setupOptimizer.summary.weak_or_adjust_setups}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Shadow trades</div>
              <div className="text-white font-semibold">{shadowSummary?.closed_shadow_trades ?? 0}</div>
            </div>
          </div>
          <div className="mb-4 border border-gray-700/70 bg-gray-900/30 rounded-lg p-3 text-sm">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <span className="text-gray-300">
                Shadow lab: {shadowSummary?.variant_states ?? 0} variantes isolees, {shadowSummary?.open_shadow_positions ?? 0} positions virtuelles ouvertes.
              </span>
              <span className={(shadowSummary?.net_shadow_pnl_eur ?? 0) >= 0 ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold'}>
                PnL shadow {formatCurrency(shadowSummary?.net_shadow_pnl_eur)}
              </span>
            </div>
          </div>
          {optimizerRows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2">Paire</th>
                    <th className="text-left py-2">Regime</th>
                    <th className="text-left py-2">Variante choisie</th>
                    <th className="text-right py-2">Score</th>
                    <th className="text-right py-2">Range</th>
                    <th className="text-right py-2">Shadow</th>
                    <th className="text-left py-2 pl-4">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {optimizerRows.slice(0, 12).map((row) => (
                    <tr key={row.symbol} className="border-b border-gray-700/50">
                      <td className="py-2 text-white">{row.symbol}</td>
                      <td className="py-2 text-gray-300">{row.current_context.regime ?? 'unknown'}</td>
                      <td className="py-2 text-gray-300">{row.selected_variant?.name ?? 'En attente'}</td>
                      <td className="py-2 text-right text-gray-300">{row.selected_variant?.score.toFixed(1) ?? 'En attente'}</td>
                      <td className="py-2 text-right text-gray-300">
                        {typeof row.selected_variant?.grid_config.range_percent === 'number' ? `${row.selected_variant.grid_config.range_percent.toFixed(2)}%` : 'En attente'}
                      </td>
                      <td className="py-2 text-right text-gray-300">
                        {typeof row.selected_variant?.shadow_metrics?.closed_trades === 'number'
                          ? `${row.selected_variant.shadow_metrics.closed_trades} / ${formatCurrency(row.selected_variant.shadow_metrics.net_pnl_eur)}`
                          : 'En attente'}
                      </td>
                      <td className="py-2 pl-4">
                        <div className={`font-semibold ${stateClass(row.status)}`}>{row.status}</div>
                        <div className="text-xs text-gray-500">{row.recommended_action}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Aucune variante paper comparable pour le moment.</div>
          )}
        </section>
      ) : null}

      {trendShadow ? (
        <section className="mb-8 bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="flex items-start gap-3">
              <TrendingUp className="w-5 h-5 text-blue-300 mt-1" />
              <div>
                <h2 className="text-xl font-bold text-white">Moteur trend shadow</h2>
                <p className="text-sm text-gray-400 mt-1">{trendShadow.message}</p>
              </div>
            </div>
            <span className="text-sm text-gray-400">{trendSummary?.symbols ?? 0} paires</span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm mb-4">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Candidats trend</div>
              <div className="text-emerald-400 font-semibold">{trendSummary?.candidate_symbols ?? 0}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Trades shadow</div>
              <div className="text-white font-semibold">{trendSummary?.closed_shadow_trades ?? 0}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Positions virtuelles</div>
              <div className="text-white font-semibold">{trendSummary?.open_shadow_positions ?? 0}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">PnL trend shadow</div>
              <div className={(trendSummary?.net_shadow_pnl_eur ?? 0) >= 0 ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold'}>
                {formatCurrency(trendSummary?.net_shadow_pnl_eur)}
              </div>
            </div>
          </div>
          <div className="mb-4 border border-blue-500/20 bg-blue-500/10 rounded-lg p-3 text-sm text-blue-100/90">
            Ce moteur observe Donchian/EMA momentum en paper shadow. Il ne remplace pas encore la grid et ne place aucun ordre officiel.
          </div>
          {trendRows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2">Paire</th>
                    <th className="text-left py-2">Meilleure variante</th>
                    <th className="text-right py-2">Score</th>
                    <th className="text-right py-2">PnL</th>
                    <th className="text-right py-2">PF</th>
                    <th className="text-right py-2">Trades</th>
                    <th className="text-left py-2 pl-4">Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {trendRows.slice(0, 12).map((row) => {
                    const best = row.best_variant;
                    return (
                      <tr key={row.symbol} className="border-b border-gray-700/50">
                        <td className="py-2 text-white">{row.symbol}</td>
                        <td className="py-2 text-gray-300">{best?.variant ?? 'En attente'}</td>
                        <td className="py-2 text-right text-gray-300">{best?.score.toFixed(1) ?? 'En attente'}</td>
                        <td className={`py-2 text-right ${(best?.net_pnl_eur ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {formatCurrency(best?.net_pnl_eur)}
                        </td>
                        <td className="py-2 text-right text-gray-300">{best?.profit_factor?.toFixed(2) ?? 'En attente'}</td>
                        <td className="py-2 text-right text-gray-300">{best?.closed_trades ?? 0}</td>
                        <td className="py-2 pl-4">
                          <div className={`font-semibold ${stateClass(best?.status)}`}>{best?.status ?? 'learning'}</div>
                          <div className="text-xs text-gray-500">{best?.last_decision?.reason ?? 'En attente de signal trend'}</div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Aucune donnee trend shadow pour le moment.</div>
          )}
        </section>
      ) : null}

      <div className="grid grid-cols-1 2xl:grid-cols-2 gap-6 mb-8">
        <section className="bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <h2 className="text-xl font-bold text-white">Qualite validation paper</h2>
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
                <span className="text-gray-400">PBO - risque surapprentissage</span>
                <span className={stateClass(quality?.pbo.status)}>{quality?.pbo.status ?? 'indisponible'}</span>
              </div>
              <div className="text-white font-semibold mt-1">{formatPct(quality?.pbo.probability, 100)}</div>
              <div className="text-xs text-gray-500 mt-1">{qualityReason('pbo', quality?.pbo.reason, quality)}</div>
            </div>
            <div className="border border-gray-700 rounded-lg p-3">
              <div className="flex justify-between">
                <span className="text-gray-400">DSR - Sharpe ajuste</span>
                <span className={stateClass(quality?.dsr.status)}>{quality?.dsr.status ?? 'indisponible'}</span>
              </div>
              <div className="text-white font-semibold mt-1">{formatPct(quality?.dsr.probability, 100)}</div>
              <div className="text-xs text-gray-500 mt-1">{qualityReason('dsr', quality?.dsr.reason, quality)}</div>
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
