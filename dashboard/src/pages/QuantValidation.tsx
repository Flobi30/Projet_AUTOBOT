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

type StrategyRouterEngine = {
  engine: string;
  variant: string | null;
  status: string;
  router_score: number;
  raw_score: number;
  net_pnl_eur: number;
  profit_factor: number | null;
  win_rate: number | null;
  closed_trades: number;
  last_decision?: {
    reason?: string;
  };
};

type StrategyRouterRoute = {
  symbol: string;
  selected_engine: string;
  selected_variant: string | null;
  router_score: number;
  status: string;
  recommended_action: string;
  reason: string;
  live_promotion_allowed: boolean;
  official_execution_enabled: boolean;
  paper_official_execution_enabled?: boolean;
  opportunity_score?: number | null;
  paper_execution_policy?: {
    support: string;
    reason: string;
    paper_execution_enabled?: boolean;
    live_enabled: boolean;
  };
  engines: StrategyRouterEngine[];
};

type StrategyReconciliationAttention = {
  symbol: string;
  verdict: string;
  recommended_action: string;
  root_causes: string[];
  official_net_pnl_eur?: number | null;
  best_shadow_engine?: string | null;
  best_shadow_net_pnl_eur?: number | null;
};

type StrategyRouterResponse = {
  enabled: boolean;
  paper_only: boolean;
  live_promotion_allowed: boolean;
  official_execution_enabled: boolean;
  paper_official_execution_enabled?: boolean;
  summary: {
    symbols: number;
    candidate_symbols: number;
    learning_symbols: number;
    no_trade_symbols: number;
  };
  routes: StrategyRouterRoute[];
  reconciliation?: {
    paper_only: boolean;
    live_promotion_allowed: boolean;
    summary?: {
      requires_attention?: number;
      verdict_counts?: Record<string, number>;
      official?: {
        closed_trades?: number;
        net_pnl_eur?: number;
        profit_factor?: number | null;
        win_rate?: number;
        source?: string;
      };
      shadow?: Record<string, {
        closed_shadow_trades?: number;
        net_shadow_pnl_eur?: number;
        candidate_symbols?: number;
      }>;
    };
    requires_attention?: StrategyReconciliationAttention[];
    message?: string;
  };
  message: string;
};

type StrategyTradeReconciliationRow = {
  symbol: string;
  verdict: string;
  root_causes: string[];
  official: {
    realized_pnl_eur?: number | null;
    return_bps?: number | null;
    fee_bps?: number | null;
    closed_at?: string | null;
  };
  matched_shadow?: {
    engine?: string | null;
    variant?: string | null;
    realized_pnl_eur?: number | null;
    return_bps?: number | null;
    fee_bps?: number | null;
    closed_at?: string | null;
  } | null;
  deltas: {
    pnl_delta_eur?: number | null;
    return_delta_bps?: number | null;
    fee_delta_bps?: number | null;
    time_delta_minutes?: number | null;
  };
};

type StrategyTradeReconciliationResponse = {
  paper_only: boolean;
  live_promotion_allowed: boolean;
  summary: {
    official_closes_loaded: number;
    shadow_closes_loaded: number;
    matched_count: number;
    no_match_count: number;
    official_loss_shadow_win_count: number;
    requires_attention: number;
    avg_pnl_delta_eur?: number | null;
    avg_return_delta_bps?: number | null;
    avg_fee_delta_bps?: number | null;
  };
  rows: StrategyTradeReconciliationRow[];
  message: string;
};

type StrategyGovernanceRow = {
  symbol: string;
  selected_engine: string;
  selected_variant?: string | null;
  governance_status: string;
  decision: string;
  execution_mode: string;
  official_execution_engine: string;
  allow_grid_entries: boolean;
  allow_shadow_signal_mirror: boolean;
  block_new_entries: boolean;
  reason?: string;
  reasons: string[];
};

type StrategyGovernanceResponse = {
  summary: {
    symbols: number;
    eligible_symbols: number;
    blocked_symbols: number;
    mirror_symbols: number;
    pending_flat_symbols: number;
  };
  symbols: StrategyGovernanceRow[];
  message: string;
};

type DecisionLedgerRow = {
  created_at?: string;
  symbol: string;
  engine?: string | null;
  event_type: string;
  event_status?: string | null;
  reason?: string | null;
  source: string;
};

type DecisionLedgerResponse = {
  summary: {
    events: number;
    by_type: Record<string, number>;
  };
  rows: DecisionLedgerRow[];
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
  if (state === 'candidate' || state === 'acceptable' || state === 'normal' || state === 'paper_review_candidate' || state === 'paper_candidate_needs_review' || state === 'aligned_win' || state === 'official_better' || state === 'eligible') return 'text-emerald-400';
  if (state === 'unsafe' || state === 'high_overfit_risk' || state === 'extreme' || state === 'execution_drag' || state === 'official_loss_shadow_win' || state === 'blocked') return 'text-red-400';
  if (state === 'weak' || state === 'caution' || state === 'high' || state === 'rising' || state === 'not_validated' || state === 'watch' || state === 'adjust' || state === 'pause_current' || state === 'learning' || state === 'no_shadow_match' || state === 'aligned_loss' || state === 'review' || state === 'pending_flat') return 'text-amber-400';
  return 'text-gray-300';
};

const QuantValidation: React.FC = () => {
  const [data, setData] = useState<QuantValidationResponse | null>(null);
  const [setupAudit, setSetupAudit] = useState<SetupAuditResponse | null>(null);
  const [setupOptimizer, setSetupOptimizer] = useState<SetupOptimizerResponse | null>(null);
  const [trendShadow, setTrendShadow] = useState<TrendShadowResponse | null>(null);
  const [meanReversionShadow, setMeanReversionShadow] = useState<TrendShadowResponse | null>(null);
  const [strategyRouter, setStrategyRouter] = useState<StrategyRouterResponse | null>(null);
  const [tradeReconciliation, setTradeReconciliation] = useState<StrategyTradeReconciliationResponse | null>(null);
  const [strategyGovernance, setStrategyGovernance] = useState<StrategyGovernanceResponse | null>(null);
  const [decisionLedger, setDecisionLedger] = useState<DecisionLedgerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [
          response,
          setupResponse,
          optimizerResponse,
          trendResponse,
          meanReversionResponse,
          routerResponse,
          tradeReconciliationResponse,
          governanceResponse,
          decisionLedgerResponse,
        ] = await Promise.all([
          apiFetch('/api/quant/validation'),
          apiFetch('/api/performance/setup-audit'),
          apiFetch('/api/setup-optimizer'),
          apiFetch('/api/trend-shadow'),
          apiFetch('/api/mean-reversion-shadow'),
          apiFetch('/api/strategy-router'),
          apiFetch('/api/strategy-reconciliation/trades'),
          apiFetch('/api/strategy-governance'),
          apiFetch('/api/decision-ledger?limit=25'),
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
        setMeanReversionShadow(meanReversionResponse.ok ? await meanReversionResponse.json() : null);
        setStrategyRouter(routerResponse.ok ? await routerResponse.json() : null);
        setTradeReconciliation(tradeReconciliationResponse.ok ? await tradeReconciliationResponse.json() : null);
        setStrategyGovernance(governanceResponse.ok ? await governanceResponse.json() : null);
        setDecisionLedger(decisionLedgerResponse.ok ? await decisionLedgerResponse.json() : null);
        setError(null);
      } catch {
        setError('Erreur lors de la recuperation de la validation quant');
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 60000);
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
  const meanSummary = meanReversionShadow?.summary;
  const meanRows = meanReversionShadow?.symbols ?? [];
  const routerRows = strategyRouter?.routes ?? [];
  const reconciliation = strategyRouter?.reconciliation;
  const tradeReconciliationRows = tradeReconciliation?.rows ?? [];
  const governanceRows = strategyGovernance?.symbols ?? [];
  const decisionLedgerRows = decisionLedger?.rows ?? [];

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

      {strategyRouter ? (
        <section className="mb-8 bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="flex items-start gap-3">
              <BrainCircuit className="w-5 h-5 text-violet-300 mt-1" />
              <div>
                <h2 className="text-xl font-bold text-white">Routeur multi-moteurs</h2>
                <p className="text-sm text-gray-400 mt-1">{strategyRouter.message}</p>
              </div>
            </div>
            <span className="text-sm text-gray-400">{strategyRouter.summary.symbols} paires</span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm mb-4">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Candidats</div>
              <div className="text-emerald-400 font-semibold">{strategyRouter.summary.candidate_symbols}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Learning</div>
              <div className="text-white font-semibold">{strategyRouter.summary.learning_symbols}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">No-trade</div>
              <div className="text-amber-400 font-semibold">{strategyRouter.summary.no_trade_symbols}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Execution paper</div>
              <div className="text-white font-semibold">
                {(strategyRouter.paper_official_execution_enabled ?? strategyRouter.official_execution_enabled) ? 'Controlee' : 'Observation'}
              </div>
              <div className="text-xs text-gray-500">Live bloque</div>
            </div>
          </div>
          <div className="mb-4 border border-violet-500/20 bg-violet-500/10 rounded-lg p-3 text-sm text-violet-100/90">
            Le routeur compare grid, trend, mean-reversion et abstention. Les meilleurs candidats peuvent maintenant passer en execution paper controlee via la gouvernance; le live reste bloque.
          </div>
          {routerRows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2">Paire</th>
                    <th className="text-left py-2">Moteur choisi</th>
                    <th className="text-right py-2">Score</th>
                    <th className="text-right py-2">Opp.</th>
                    <th className="text-left py-2 pl-4">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {routerRows.slice(0, 14).map((row) => (
                    <tr key={row.symbol} className="border-b border-gray-700/50">
                      <td className="py-2 text-white">{row.symbol}</td>
                      <td className="py-2 text-gray-300">
                        {row.selected_engine}
                        <span className="text-gray-500"> / {row.selected_variant ?? 'abstain'}</span>
                      </td>
                      <td className="py-2 text-right text-gray-300">{row.router_score.toFixed(1)}</td>
                      <td className="py-2 text-right text-gray-300">{row.opportunity_score?.toFixed(1) ?? 'En attente'}</td>
                      <td className="py-2 pl-4">
                        <div className={`font-semibold ${stateClass(row.status)}`}>{row.recommended_action}</div>
                        <div className="text-xs text-gray-500">{row.reason}</div>
                        <div className="text-xs text-gray-500">{row.paper_execution_policy?.support ?? 'shadow_only'}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Aucune route multi-moteurs pour le moment.</div>
          )}
        </section>
      ) : null}

      {strategyGovernance ? (
        <section className="mb-8 bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="flex items-start gap-3">
              <ShieldCheck className="w-5 h-5 text-emerald-300 mt-1" />
              <div>
                <h2 className="text-xl font-bold text-white">Gouvernance paper officielle</h2>
                <p className="text-sm text-gray-400 mt-1">
                  Ce niveau transforme le router + la reconciliation en politique d'execution concrete.
                </p>
              </div>
            </div>
            <span className="text-sm text-gray-400">{strategyGovernance.summary.symbols} paires</span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 text-sm mb-4">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Eligibles</div>
              <div className="text-emerald-400 font-semibold">{strategyGovernance.summary.eligible_symbols}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Bloquees</div>
              <div className="text-red-400 font-semibold">{strategyGovernance.summary.blocked_symbols}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Mirror non-grid</div>
              <div className="text-white font-semibold">{strategyGovernance.summary.mirror_symbols}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">En attente flat</div>
              <div className="text-amber-300 font-semibold">{strategyGovernance.summary.pending_flat_symbols}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Live</div>
              <div className="text-white font-semibold">Bloque</div>
            </div>
          </div>
          {governanceRows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2">Paire</th>
                    <th className="text-left py-2">Moteur cible</th>
                    <th className="text-left py-2">Statut</th>
                    <th className="text-left py-2">Mode</th>
                    <th className="text-left py-2">Decision</th>
                    <th className="text-left py-2 pl-4">Raison</th>
                  </tr>
                </thead>
                <tbody>
                  {governanceRows.slice(0, 14).map((row) => (
                    <tr key={`${row.symbol}-${row.selected_engine}`} className="border-b border-gray-700/50">
                      <td className="py-2 text-white">{row.symbol}</td>
                      <td className="py-2 text-gray-300">
                        {row.selected_engine}
                        <span className="text-gray-500"> / {row.selected_variant ?? 'n/a'}</span>
                      </td>
                      <td className={`py-2 font-semibold ${stateClass(row.governance_status)}`}>{row.governance_status}</td>
                      <td className="py-2 text-gray-300">{row.execution_mode}</td>
                      <td className="py-2 text-gray-300">{row.decision}</td>
                      <td className="py-2 pl-4">
                        <div className="text-gray-300">{row.reason ?? row.reasons?.[0] ?? 'Aucune raison'}</div>
                        <div className="text-xs text-gray-500">
                          grid {row.allow_grid_entries ? 'autorise' : 'bloque'} | mirror {row.allow_shadow_signal_mirror ? 'oui' : 'non'}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Aucune politique de gouvernance disponible pour le moment.</div>
          )}
        </section>
      ) : null}

      {reconciliation ? (
        <section className="mb-8 bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="flex items-start gap-3">
              <ShieldCheck className="w-5 h-5 text-amber-300 mt-1" />
              <div>
                <h2 className="text-xl font-bold text-white">Concordance shadow / paper officiel</h2>
                <p className="text-sm text-gray-400 mt-1">
                  Les resultats shadow sont compares au ledger paper officiel avant toute promotion.
                </p>
              </div>
            </div>
            <span className={(reconciliation.summary?.requires_attention ?? 0) > 0 ? 'text-amber-300 text-sm font-semibold' : 'text-emerald-300 text-sm font-semibold'}>
              {reconciliation.summary?.requires_attention ?? 0} point(s) a verifier
            </span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm mb-4">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Clotures officielles</div>
              <div className="text-white font-semibold">{reconciliation.summary?.official?.closed_trades ?? 0}</div>
              <div className="text-xs text-gray-500">{reconciliation.summary?.official?.source ?? 'source inconnue'}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">PnL officiel</div>
              <div className={(reconciliation.summary?.official?.net_pnl_eur ?? 0) >= 0 ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold'}>
                {formatCurrency(reconciliation.summary?.official?.net_pnl_eur)}
              </div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">PF officiel</div>
              <div className="text-white font-semibold">{reconciliation.summary?.official?.profit_factor?.toFixed(2) ?? 'En attente'}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Live promotion</div>
              <div className="text-white font-semibold">{reconciliation.live_promotion_allowed ? 'Autorisee' : 'Bloquee'}</div>
              <div className="text-xs text-gray-500">Paper-only</div>
            </div>
          </div>
          {reconciliation.requires_attention?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2">Paire</th>
                    <th className="text-left py-2">Verdict</th>
                    <th className="text-right py-2">Paper officiel</th>
                    <th className="text-right py-2">Meilleur shadow</th>
                    <th className="text-left py-2 pl-4">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {reconciliation.requires_attention.slice(0, 10).map((row) => (
                    <tr key={`${row.symbol}-${row.verdict}`} className="border-b border-gray-700/50">
                      <td className="py-2 text-white">{row.symbol}</td>
                      <td className={`py-2 font-semibold ${stateClass(row.verdict)}`}>{row.verdict}</td>
                      <td className={`py-2 text-right ${(row.official_net_pnl_eur ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {formatCurrency(row.official_net_pnl_eur ?? undefined)}
                      </td>
                      <td className={`py-2 text-right ${(row.best_shadow_net_pnl_eur ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {row.best_shadow_engine ?? 'none'} / {formatCurrency(row.best_shadow_net_pnl_eur ?? undefined)}
                      </td>
                      <td className="py-2 pl-4">
                        <div className="text-gray-300">{row.recommended_action}</div>
                        <div className="text-xs text-gray-500">{row.root_causes.slice(0, 3).join(', ') || 'Aucune cause precise'}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-400 text-sm">
              Aucun ecart prioritaire detecte entre le shadow et le ledger paper officiel.
            </div>
          )}
          <div className="mt-4 border border-amber-500/20 bg-amber-500/10 rounded-lg p-3 text-sm text-amber-100/90">
            Un shadow positif seul ne suffit pas: il doit etre confirme par des clotures paper officielles, avec un echantillon robuste.
          </div>
        </section>
      ) : null}

      {decisionLedger ? (
        <section className="mb-8 bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="flex items-start gap-3">
              <Activity className="w-5 h-5 text-orange-300 mt-1" />
              <div>
                <h2 className="text-xl font-bold text-white">Ledger de decision</h2>
                <p className="text-sm text-gray-400 mt-1">
                  Source canonique des derniers evenements signal, decision, ordre et erreur.
                </p>
              </div>
            </div>
            <span className="text-sm text-gray-400">{decisionLedger.summary.events} evenements</span>
          </div>
          {decisionLedgerRows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2">Horodatage</th>
                    <th className="text-left py-2">Paire</th>
                    <th className="text-left py-2">Type</th>
                    <th className="text-left py-2">Statut</th>
                    <th className="text-left py-2">Moteur</th>
                    <th className="text-left py-2 pl-4">Raison</th>
                  </tr>
                </thead>
                <tbody>
                  {decisionLedgerRows.slice(0, 20).map((row, index) => (
                    <tr key={`${row.created_at ?? 'na'}-${row.symbol}-${index}`} className="border-b border-gray-700/50">
                      <td className="py-2 text-gray-300">{row.created_at ? new Date(row.created_at).toLocaleString('fr-FR') : 'n/a'}</td>
                      <td className="py-2 text-white">{row.symbol}</td>
                      <td className="py-2 text-gray-300">{row.event_type}</td>
                      <td className={`py-2 ${stateClass(row.event_status ?? undefined)}`}>{row.event_status ?? 'n/a'}</td>
                      <td className="py-2 text-gray-300">{row.engine ?? 'n/a'}</td>
                      <td className="py-2 pl-4">
                        <div className="text-gray-300">{row.reason ?? 'Aucune raison'}</div>
                        <div className="text-xs text-gray-500">{row.source}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Aucun evenement de decision recente pour le moment.</div>
          )}
        </section>
      ) : null}

      {tradeReconciliation ? (
        <section className="mb-8 bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="flex items-start gap-3">
              <SlidersHorizontal className="w-5 h-5 text-cyan-300 mt-1" />
              <div>
                <h2 className="text-xl font-bold text-white">Audit trade par trade</h2>
                <p className="text-sm text-gray-400 mt-1">
                  Les clotures paper officielles sont rapprochees des clotures shadow les plus proches par paire et par temps.
                </p>
              </div>
            </div>
            <span className={(tradeReconciliation.summary.requires_attention ?? 0) > 0 ? 'text-amber-300 text-sm font-semibold' : 'text-emerald-300 text-sm font-semibold'}>
              {tradeReconciliation.summary.requires_attention ?? 0} divergence(s)
            </span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm mb-4">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Clotures officielles</div>
              <div className="text-white font-semibold">{tradeReconciliation.summary.official_closes_loaded}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Match shadow</div>
              <div className="text-white font-semibold">{tradeReconciliation.summary.matched_count}</div>
              <div className="text-xs text-gray-500">{tradeReconciliation.summary.no_match_count} sans match</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Officiel perd / shadow gagne</div>
              <div className="text-amber-300 font-semibold">{tradeReconciliation.summary.official_loss_shadow_win_count}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Delta PnL moyen</div>
              <div className={(tradeReconciliation.summary.avg_pnl_delta_eur ?? 0) >= 0 ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold'}>
                {formatCurrency(tradeReconciliation.summary.avg_pnl_delta_eur ?? undefined)}
              </div>
              <div className="text-xs text-gray-500">officiel - shadow</div>
            </div>
          </div>
          {tradeReconciliationRows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-gray-400">
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-2">Paire</th>
                    <th className="text-left py-2">Verdict</th>
                    <th className="text-right py-2">Officiel</th>
                    <th className="text-right py-2">Shadow proche</th>
                    <th className="text-right py-2">Delta</th>
                    <th className="text-left py-2 pl-4">Cause</th>
                  </tr>
                </thead>
                <tbody>
                  {tradeReconciliationRows.slice(0, 12).map((row, index) => (
                    <tr key={`${row.symbol}-${row.verdict}-${index}`} className="border-b border-gray-700/50">
                      <td className="py-2 text-white">{row.symbol}</td>
                      <td className={`py-2 font-semibold ${stateClass(row.verdict)}`}>{row.verdict}</td>
                      <td className={`py-2 text-right ${(row.official.realized_pnl_eur ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        <div>{formatCurrency(row.official.realized_pnl_eur ?? undefined)}</div>
                        <div className="text-xs text-gray-500">{formatBps(row.official.return_bps ?? undefined)}</div>
                      </td>
                      <td className={`py-2 text-right ${(row.matched_shadow?.realized_pnl_eur ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        <div>{row.matched_shadow?.engine ?? 'aucun'} / {formatCurrency(row.matched_shadow?.realized_pnl_eur ?? undefined)}</div>
                        <div className="text-xs text-gray-500">{formatBps(row.matched_shadow?.return_bps ?? undefined)}</div>
                      </td>
                      <td className={`py-2 text-right ${(row.deltas.pnl_delta_eur ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        <div>{formatCurrency(row.deltas.pnl_delta_eur ?? undefined)}</div>
                        <div className="text-xs text-gray-500">{formatBps(row.deltas.return_delta_bps ?? undefined)}</div>
                      </td>
                      <td className="py-2 pl-4">
                        <div className="text-gray-300">{row.root_causes.slice(0, 3).join(', ') || 'Aucune cause precise'}</div>
                        <div className="text-xs text-gray-500">{row.deltas.time_delta_minutes ?? 'n/a'} min d'ecart</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-400 text-sm">
              Aucune cloture officielle recente a comparer pour le moment.
            </div>
          )}
          <div className="mt-4 border border-cyan-500/20 bg-cyan-500/10 rounded-lg p-3 text-sm text-cyan-100/90">
            Ce rapprochement est approximatif: il explique les ecarts d'execution, frais et timing, mais ne certifie pas que les deux moteurs ont pris exactement le meme setup.
          </div>
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
            Ce moteur observe Donchian/EMA momentum en shadow. S'il devient assez robuste et que la gouvernance l'autorise, il peut etre miroite vers le paper officiel sans toucher au live.
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

      {meanReversionShadow ? (
        <section className="mb-8 bg-gray-800 border border-gray-700/60 rounded-xl p-4 lg:p-6">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div className="flex items-start gap-3">
              <SlidersHorizontal className="w-5 h-5 text-cyan-300 mt-1" />
              <div>
                <h2 className="text-xl font-bold text-white">Moteur mean-reversion shadow</h2>
                <p className="text-sm text-gray-400 mt-1">{meanReversionShadow.message}</p>
              </div>
            </div>
            <span className="text-sm text-gray-400">{meanSummary?.symbols ?? 0} paires</span>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm mb-4">
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Candidats MR</div>
              <div className="text-emerald-400 font-semibold">{meanSummary?.candidate_symbols ?? 0}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Trades shadow</div>
              <div className="text-white font-semibold">{meanSummary?.closed_shadow_trades ?? 0}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">Positions virtuelles</div>
              <div className="text-white font-semibold">{meanSummary?.open_shadow_positions ?? 0}</div>
            </div>
            <div className="bg-gray-900/50 rounded-lg p-3">
              <div className="text-gray-400">PnL MR shadow</div>
              <div className={(meanSummary?.net_shadow_pnl_eur ?? 0) >= 0 ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold'}>
                {formatCurrency(meanSummary?.net_shadow_pnl_eur)}
              </div>
            </div>
          </div>
          <div className="mb-4 border border-cyan-500/20 bg-cyan-500/10 rounded-lg p-3 text-sm text-cyan-100/90">
            Ce moteur observe les retours a la moyenne Bollinger/z-score. Il reste prudent face aux tendances fortes, mais peut lui aussi passer en mirror paper controle si la preuve est suffisante.
          </div>
          {meanRows.length ? (
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
                  {meanRows.slice(0, 12).map((row) => {
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
                          <div className="text-xs text-gray-500">{best?.last_decision?.reason ?? 'En attente de signal MR'}</div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Aucune donnee mean-reversion shadow pour le moment.</div>
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
