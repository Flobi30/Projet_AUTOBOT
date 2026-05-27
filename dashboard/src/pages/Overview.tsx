import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, BrainCircuit, CheckCircle2, Clock, ShieldAlert, TrendingUp } from 'lucide-react';
import { apiFetch } from '../api/client';

type ApiState<T> = {
  data: T | null;
  error: string | null;
};

type HealthResponse = {
  status?: string;
  components?: {
    orchestrator?: string;
    websocket?: string;
    instances?: number;
    uptime_seconds?: number;
  };
};

type CapitalResponse = {
  paper_mode?: boolean;
  source?: string;
  source_status?: string;
  total_capital?: number;
  available_cash?: number;
  autobot_trading_capital?: number | null;
  autobot_available_capital?: number | null;
  paper_realized_pnl?: number | null;
  total_profit?: number | null;
};

type PerformanceResponse = {
  profit_total?: number;
  profit_factor?: number | null;
  profit_factor_status?: string;
  win_rate?: number;
  total_trades?: number;
  instances_count?: number;
};

type MarketQualityResponse = {
  recommended_action?: string;
  summary?: {
    symbols?: number;
    healthy_symbols?: number;
    blocked_symbols?: number;
    price_missing?: number;
    book_missing_or_invalid?: number;
    backpressure_active?: boolean;
  };
};

type RuntimeTraceResponse = {
  overall_status?: 'healthy' | 'warning' | 'critical';
  trace?: {
    last_signal?: Record<string, unknown> | null;
    last_decision?: Record<string, unknown> | null;
    last_order?: Record<string, unknown> | null;
    last_error?: Record<string, unknown> | null;
  };
  safety?: {
    kill_switch?: {
      status?: string;
      tripped?: boolean;
      reason_code?: string | null;
      reason?: string | null;
    };
  };
  strategies?: {
    active_count?: number;
    pairs_watched?: string[];
  };
};

type TradingDebugResponse = {
  status?: string;
  reason?: string;
  blocking_condition?: string | null;
  paper_mode?: boolean;
  last_signal?: Record<string, unknown> | null;
  last_decision?: Record<string, unknown> | null;
  last_order?: Record<string, unknown> | null;
  last_error?: Record<string, unknown> | null;
};

const empty = <T,>(): ApiState<T> => ({ data: null, error: null });

const fetchJson = async <T,>(path: string): Promise<ApiState<T>> => {
  try {
    const response = await apiFetch(path);
    if (!response.ok) {
      return { data: null, error: `HTTP ${response.status}` };
    }
    return { data: (await response.json()) as T, error: null };
  } catch (error) {
    return { data: null, error: error instanceof Error ? error.message : 'Erreur API' };
  }
};

const formatCurrency = (value?: number | null) =>
  typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })
    : 'Non disponible';

const formatNumber = (value?: number | null, digits = 2) =>
  typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : 'Non disponible';

const formatPercent = (value?: number | null) =>
  typeof value === 'number' && Number.isFinite(value) ? `${formatNumber(value, 1)}%` : 'Non disponible';

const eventText = (event?: Record<string, unknown> | null) => {
  if (!event) return 'En attente de donnees';
  const status = event.event_status ?? event.status ?? event.action ?? event.event;
  const reason = event.reason ?? event.blocking_condition ?? event.error;
  const symbol = event.symbol ? ` ${String(event.symbol)}` : '';
  return [status, symbol, reason ? `- ${String(reason)}` : ''].filter(Boolean).join(' ');
};

const toneClasses = (status?: string | null) => {
  const value = String(status || '').toLowerCase();
  if (value.includes('critical') || value.includes('tripped') || value.includes('error') || value.includes('blocked')) {
    return 'border-red-500/30 bg-red-500/10 text-red-300';
  }
  if (value.includes('warning') || value.includes('warmup') || value.includes('pending') || value.includes('learning')) {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-300';
  }
  if (value.includes('healthy') || value.includes('ok') || value.includes('running') || value.includes('armed')) {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
  }
  return 'border-gray-700 bg-gray-800 text-gray-300';
};

const Panel: React.FC<{
  title: string;
  icon: React.ReactNode;
  status?: string | null;
  children: React.ReactNode;
}> = ({ title, icon, status, children }) => (
  <section className={`rounded-lg border p-4 min-h-[180px] ${toneClasses(status)}`}>
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-white">
        {icon}
        <h2 className="text-base font-semibold">{title}</h2>
      </div>
      {status ? <span className="text-xs font-semibold uppercase tracking-wide">{status}</span> : null}
    </div>
    <div className="mt-4 space-y-3 text-sm">{children}</div>
  </section>
);

const Row: React.FC<{ label: string; value: React.ReactNode; strong?: boolean }> = ({ label, value, strong }) => (
  <div className="flex items-start justify-between gap-4">
    <span className="text-gray-400">{label}</span>
    <span className={`text-right ${strong ? 'font-semibold text-white' : 'text-gray-200'}`}>{value}</span>
  </div>
);

const Overview: React.FC = () => {
  const [health, setHealth] = useState<ApiState<HealthResponse>>(empty);
  const [capital, setCapital] = useState<ApiState<CapitalResponse>>(empty);
  const [performance, setPerformance] = useState<ApiState<PerformanceResponse>>(empty);
  const [quality, setQuality] = useState<ApiState<MarketQualityResponse>>(empty);
  const [trace, setTrace] = useState<ApiState<RuntimeTraceResponse>>(empty);
  const [debug, setDebug] = useState<ApiState<TradingDebugResponse>>(empty);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [nextHealth, nextCapital, nextPerformance, nextQuality, nextTrace, nextDebug] = await Promise.all([
      fetchJson<HealthResponse>('/health'),
      fetchJson<CapitalResponse>('/api/capital'),
      fetchJson<PerformanceResponse>('/api/performance/global'),
      fetchJson<MarketQualityResponse>('/api/market-data/quality'),
      fetchJson<RuntimeTraceResponse>('/api/runtime/trace'),
      fetchJson<TradingDebugResponse>('/api/trading/debug'),
    ]);
    setHealth(nextHealth);
    setCapital(nextCapital);
    setPerformance(nextPerformance);
    setQuality(nextQuality);
    setTrace(nextTrace);
    setDebug(nextDebug);
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [refresh]);

  const mode = capital.data?.paper_mode ? 'PAPER' : capital.data ? 'LIVE' : 'INCONNU';
  const pnl = capital.data?.paper_realized_pnl ?? capital.data?.total_profit ?? performance.data?.profit_total ?? null;
  const pnlClass = typeof pnl === 'number' && pnl >= 0 ? 'text-emerald-300' : 'text-red-300';
  const currentBlock = debug.data?.blocking_condition || debug.data?.reason || trace.data?.overall_status || 'Non disponible';
  const marketSummary = quality.data?.summary;

  const topStatus = useMemo(() => {
    if (health.error || trace.error || debug.error) return 'warning';
    if (trace.data?.overall_status) return trace.data.overall_status;
    if (health.data?.status) return health.data.status;
    return loading ? 'loading' : 'unknown';
  }, [debug.error, health.data?.status, health.error, loading, trace.data?.overall_status, trace.error]);

  return (
    <div className="min-h-screen bg-gray-900 p-4 sm:p-6 lg:p-8">
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Vue simple AUTOBOT</h1>
          <p className="mt-1 text-sm text-gray-400">Sante, PnL, risque, decisions et blocage actuel.</p>
        </div>
        <button
          onClick={refresh}
          className="inline-flex h-10 items-center justify-center rounded-md border border-gray-700 bg-gray-800 px-4 text-sm font-medium text-gray-200 hover:bg-gray-700"
        >
          Actualiser
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Panel title="Sante" icon={<Activity className="h-5 w-5 text-emerald-300" />} status={topStatus}>
          <Row label="Backend" value={health.error ?? health.data?.status ?? 'Non disponible'} strong />
          <Row label="Orchestrateur" value={health.data?.components?.orchestrator ?? 'Non disponible'} />
          <Row label="Websocket" value={health.data?.components?.websocket ?? 'Non disponible'} />
          <Row label="Instances/paires" value={health.data?.components?.instances ?? trace.data?.strategies?.active_count ?? 'Non disponible'} />
        </Panel>

        <Panel title="PnL" icon={<TrendingUp className="h-5 w-5 text-emerald-300" />} status={mode}>
          <Row label="Mode" value={mode} strong />
          <Row label="Capital AUTOBOT" value={formatCurrency(capital.data?.autobot_trading_capital ?? capital.data?.total_capital)} />
          <Row label="Disponible" value={formatCurrency(capital.data?.autobot_available_capital ?? capital.data?.available_cash)} />
          <Row label="PnL realise" value={<span className={pnlClass}>{formatCurrency(pnl)}</span>} strong />
          <Row label="Profit factor" value={formatNumber(performance.data?.profit_factor)} />
        </Panel>

        <Panel title="Risque" icon={<ShieldAlert className="h-5 w-5 text-amber-300" />} status={trace.data?.safety?.kill_switch?.tripped ? 'tripped' : trace.data?.safety?.kill_switch?.status}>
          <Row label="Kill switch" value={trace.data?.safety?.kill_switch?.status ?? 'Non disponible'} strong />
          <Row label="Declenche" value={trace.data?.safety?.kill_switch?.tripped ? 'Oui' : 'Non'} />
          <Row label="Carnets invalides" value={marketSummary?.book_missing_or_invalid ?? 'Non disponible'} />
          <Row label="Paires bloquees" value={marketSummary?.blocked_symbols ?? 'Non disponible'} />
          <Row label="Backpressure" value={marketSummary?.backpressure_active ? 'Actif' : 'Non'} />
        </Panel>

        <Panel title="Decision" icon={<BrainCircuit className="h-5 w-5 text-blue-300" />} status={debug.data?.status}>
          <Row label="Pipeline" value={debug.error ?? debug.data?.status ?? 'Non disponible'} strong />
          <Row label="Dernier signal" value={eventText(debug.data?.last_signal ?? trace.data?.trace?.last_signal)} />
          <Row label="Derniere decision" value={eventText(debug.data?.last_decision ?? trace.data?.trace?.last_decision)} />
          <Row label="Dernier ordre" value={eventText(debug.data?.last_order ?? trace.data?.trace?.last_order)} />
        </Panel>

        <Panel title="Blocage" icon={<AlertTriangle className="h-5 w-5 text-amber-300" />} status={currentBlock}>
          <Row label="Condition" value={currentBlock} strong />
          <Row label="Raison" value={debug.data?.reason ?? 'Non disponible'} />
          <Row label="Qualite marche" value={quality.error ?? quality.data?.recommended_action ?? 'Non disponible'} />
          <Row label="Win rate" value={formatPercent(performance.data?.win_rate)} />
          <Row label="Trades clotures" value={performance.data?.total_trades ?? 'Non disponible'} />
        </Panel>
      </div>

      <div className="mt-4 rounded-lg border border-gray-700 bg-gray-800 p-4 text-sm text-gray-300">
        <div className="flex items-start gap-3">
          {topStatus === 'healthy' ? <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-300" /> : <Clock className="mt-0.5 h-5 w-5 text-amber-300" />}
          <div>
            <div className="font-semibold text-white">Lecture rapide</div>
            <p className="mt-1">
              En paper, les montants sont virtuels. Le live reste bloque tant qu'il n'est pas active explicitement et valide humainement.
              Les pages detaillees restent disponibles par URL pour l'audit, mais la navigation normale reste volontairement simple.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Overview;
