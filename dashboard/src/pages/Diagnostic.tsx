import React, { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../api/client';
import {
  Activity,
  Server,
  Database,
  Wifi,
  Cpu,
  HardDrive,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Terminal,
  HeartPulse,
  Clock,
  Wallet,
  ListChecks,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface SystemMetrics {
  cpu: { percent: number; status: 'healthy' | 'warning' | 'critical' };
  memory: { percent: number; used_gb: number; total_gb: number; status: 'healthy' | 'warning' | 'critical' };
  disk: { percent: number; used_gb: number; total_gb: number; status: 'healthy' | 'warning' | 'critical' };
  timestamp: string;
}

interface RuntimeCheck {
  name: string;
  ok: boolean;
  status: string;
}

interface RuntimeTrace {
  timestamp: string;
  overall_status: 'healthy' | 'warning' | 'critical';
  mode: 'paper' | 'live';
  paper_mode: boolean;
  runtime: {
    running: boolean;
    websocket_connected: boolean;
    uptime_seconds: number | null;
    instance_count: number;
  };
  strategies: {
    active_count: number;
    names: string[];
    pairs_watched: string[];
    warmup_or_blocked: Array<{
      id: string;
      name: string;
      symbol: string;
      warmup?: { price_samples?: number; required_samples?: number };
      blocked_reasons?: string[];
    }>;
  };
  database: {
    state: { status?: string; accessible?: boolean; tables?: Record<string, { exists?: boolean; rows?: number }> };
    paper: { status?: string; accessible?: boolean; tables?: Record<string, { exists?: boolean; rows?: number }> };
  };
  order_executor: {
    class_name: string | null;
    open_orders_status: string;
    open_orders_count: number | null;
    recorded_trades_count: number;
  };
  capital?: {
    paper_mode?: boolean;
    source?: string;
    source_status?: string;
    total_capital?: number;
    available_cash?: number;
  };
  trace: {
    last_market_tick?: Record<string, unknown> | null;
    last_signal?: Record<string, unknown> | null;
    last_decision?: Record<string, unknown> | null;
    last_order?: Record<string, unknown> | null;
    last_trade?: Record<string, unknown> | null;
    last_error?: Record<string, unknown> | null;
    recent_errors?: Array<Record<string, unknown>>;
  };
  checks: RuntimeCheck[];
  messages: string[];
}

const statusLabel = {
  healthy: 'Operationnel',
  warning: 'A verifier',
  critical: 'Critique',
};

const statusStyle = {
  healthy: {
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/30',
    text: 'text-emerald-400',
    dot: 'bg-emerald-400',
  },
  warning: {
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    text: 'text-amber-300',
    dot: 'bg-amber-400',
  },
  critical: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    text: 'text-red-400',
    dot: 'bg-red-400',
  },
};

const formatUptime = (seconds: number | null | undefined): string => {
  if (!seconds) return 'Non disponible';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
};

const formatDate = (value?: string | null) => {
  if (!value) return 'Non disponible';
  return new Date(value).toLocaleString('fr-FR');
};

const formatCurrency = (value?: number) =>
  typeof value === 'number'
    ? value.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })
    : 'Non disponible';

const toStatus = (ok?: boolean): 'healthy' | 'warning' | 'critical' => (ok ? 'healthy' : 'critical');

const StatusBadge: React.FC<{ status: 'healthy' | 'warning' | 'critical' }> = ({ status }) => {
  const style = statusStyle[status];
  const Icon = status === 'healthy' ? CheckCircle : status === 'warning' ? AlertTriangle : XCircle;
  return (
    <span className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold border ${style.bg} ${style.text} ${style.border}`}>
      <Icon className="w-4 h-4" />
      {statusLabel[status]}
    </span>
  );
};

const ProgressBar: React.FC<{
  value: number;
  status: 'healthy' | 'warning' | 'critical';
  label: string;
}> = ({ value, status, label }) => {
  const colors = {
    healthy: 'bg-emerald-500',
    warning: 'bg-yellow-500',
    critical: 'bg-red-500',
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span className="text-gray-400">{label}</span>
        <span className={`font-bold ${statusStyle[status].text}`}>{value}%</span>
      </div>
      <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${colors[status]} transition-all duration-500 rounded-full`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
    </div>
  );
};

const ServiceCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  status: 'healthy' | 'warning' | 'critical';
  details: string[];
}> = ({ icon, title, status, details }) => {
  const style = statusStyle[status];
  return (
    <div className={`${style.bg} border ${style.border} rounded-2xl p-6`}>
      <div className="flex items-center gap-3 mb-4">
        <div className={`p-2 bg-gray-800 rounded-xl ${style.text}`}>{icon}</div>
        <div>
          <h3 className="font-bold text-white">{title}</h3>
          <div className="flex items-center gap-2 mt-1">
            <span className={`w-2 h-2 rounded-full ${style.dot}`} />
            <span className={`text-sm ${style.text}`}>{statusLabel[status]}</span>
          </div>
        </div>
      </div>
      <div className="space-y-2 pt-4 border-t border-gray-700/50">
        {details.map((detail) => (
          <div key={detail} className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-1.5 h-1.5 bg-gray-500 rounded-full" />
            {detail}
          </div>
        ))}
      </div>
    </div>
  );
};

const TraceRow: React.FC<{ label: string; event?: Record<string, unknown> | null }> = ({ label, event }) => {
  const timestamp = typeof event?.timestamp === 'string' ? event.timestamp : null;
  const symbol = typeof event?.symbol === 'string' ? event.symbol : null;
  const detail = event
    ? [
        typeof event.event === 'string' ? event.event : null,
        typeof event.reason === 'string' ? event.reason : null,
        typeof event.status === 'string' ? event.status : null,
        typeof event.source === 'string' ? event.source : null,
      ].filter(Boolean).join(' / ') || 'Evenement recu'
    : 'En attente de donnees';

  return (
    <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 p-3 bg-gray-700/30 rounded-xl">
      <div>
        <div className="text-white font-medium">{label}</div>
        <div className="text-gray-400 text-sm">{detail}</div>
      </div>
      <div className="text-right text-sm">
        <div className="text-emerald-300">{symbol || 'Non disponible'}</div>
        <div className="text-gray-500">{formatDate(timestamp)}</div>
      </div>
    </div>
  );
};

const Diagnostic: React.FC = () => {
  const [systemMetrics, setSystemMetrics] = useState<SystemMetrics | null>(null);
  const [runtimeTrace, setRuntimeTrace] = useState<RuntimeTrace | null>(null);
  const [loading, setLoading] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<{ time: string; ram: number; cpu: number }[]>([]);

  const fetchDiagnostics = useCallback(async () => {
    try {
      setError(null);
      const [systemRes, traceRes] = await Promise.all([
        apiFetch('/api/system'),
        apiFetch('/api/runtime/trace'),
      ]);

      if (!systemRes.ok) throw new Error(`API system indisponible: ${systemRes.status}`);
      if (!traceRes.ok) throw new Error(`API runtime indisponible: ${traceRes.status}`);

      const systemData: SystemMetrics = await systemRes.json();
      const traceData: RuntimeTrace = await traceRes.json();
      setSystemMetrics(systemData);
      setRuntimeTrace(traceData);

      const now = new Date();
      const timeStr = `${now.getHours()}:${now.getMinutes().toString().padStart(2, '0')}`;
      setHistory((prev) => [...prev, { time: timeStr, ram: systemData.memory.percent, cpu: systemData.cpu.percent }].slice(-24));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de connexion');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDiagnostics();
    const interval = setInterval(fetchDiagnostics, 5000);
    return () => clearInterval(interval);
  }, [fetchDiagnostics]);

  const refreshStatus = async () => {
    setLoading(true);
    await fetchDiagnostics();
    setLoading(false);
  };

  const systemOverall = (): 'healthy' | 'warning' | 'critical' => {
    if (!systemMetrics) return 'warning';
    const statuses = [systemMetrics.cpu.status, systemMetrics.memory.status, systemMetrics.disk.status];
    if (statuses.includes('critical')) return 'critical';
    if (statuses.includes('warning')) return 'warning';
    return 'healthy';
  };

  const overallStatus = (() => {
    const sys = systemOverall();
    if (sys === 'critical' || runtimeTrace?.overall_status === 'critical') return 'critical';
    if (sys === 'warning' || runtimeTrace?.overall_status === 'warning') return 'warning';
    return 'healthy';
  })();

  if (isLoading) {
    return (
      <div className="p-8 bg-gray-900 min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center">
          <div className="w-12 h-12 border-4 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin" />
          <span className="mt-4 text-emerald-400">Chargement du diagnostic...</span>
        </div>
      </div>
    );
  }

  const failedChecks = runtimeTrace?.checks.filter((check) => !check.ok) ?? [];
  const recommendations = [
    ...(runtimeTrace?.messages ?? []),
    ...(failedChecks.length ? ['Verifier les logs backend avant toute relance du bot.'] : ['Aucun blocage critique verifie par les endpoints disponibles.']),
  ];

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-3">
          <div className="flex items-center space-x-3">
            <HeartPulse className={`w-6 lg:w-8 h-6 lg:h-8 ${statusStyle[overallStatus].text}`} />
            <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
              Diagnostic
            </h1>
          </div>
          <div className="flex items-center gap-4">
            <StatusBadge status={overallStatus} />
            <button
              onClick={refreshStatus}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl text-white font-bold transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Actualiser
            </button>
          </div>
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">
          Derniere mise a jour: {formatDate(runtimeTrace?.timestamp || systemMetrics?.timestamp)}
        </p>
        {error && (
          <div className="mt-3 bg-red-500/20 border border-red-500/50 rounded-lg p-3 text-red-300 text-sm">
            {error}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-xl p-6">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2">
              <Cpu className="w-5 h-5 text-emerald-400" />
              <span className="text-gray-400 text-sm font-medium">RAM</span>
            </div>
            <span className={`text-sm font-bold px-2 py-1 rounded-lg ${statusStyle[systemMetrics?.memory.status ?? 'warning'].text}`}>
              {systemMetrics?.memory.status ?? 'Non disponible'}
            </span>
          </div>
          {systemMetrics && <ProgressBar value={systemMetrics.memory.percent} status={systemMetrics.memory.status} label="RAM utilisee" />}
          <p className="mt-3 text-sm text-gray-500">
            {systemMetrics ? `${systemMetrics.memory.used_gb} GB / ${systemMetrics.memory.total_gb} GB` : 'Non disponible'}
          </p>
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-xl p-6">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-emerald-400" />
              <span className="text-gray-400 text-sm font-medium">CPU</span>
            </div>
            <span className={`text-sm font-bold px-2 py-1 rounded-lg ${statusStyle[systemMetrics?.cpu.status ?? 'warning'].text}`}>
              {systemMetrics?.cpu.status ?? 'Non disponible'}
            </span>
          </div>
          {systemMetrics && <ProgressBar value={systemMetrics.cpu.percent} status={systemMetrics.cpu.status} label="CPU utilise" />}
          <p className="mt-3 text-sm text-gray-500">Mesure runtime du backend.</p>
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-xl p-6">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2">
              <HardDrive className="w-5 h-5 text-emerald-400" />
              <span className="text-gray-400 text-sm font-medium">Disque</span>
            </div>
            <span className={`text-sm font-bold px-2 py-1 rounded-lg ${statusStyle[systemMetrics?.disk.status ?? 'warning'].text}`}>
              {systemMetrics?.disk.status ?? 'Non disponible'}
            </span>
          </div>
          {systemMetrics && <ProgressBar value={systemMetrics.disk.percent} status={systemMetrics.disk.status} label="Disque utilise" />}
          <p className="mt-3 text-sm text-gray-500">
            {systemMetrics ? `${systemMetrics.disk.used_gb} GB / ${systemMetrics.disk.total_gb} GB` : 'Non disponible'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <ServiceCard
          icon={<Server className="w-6 h-6" />}
          title="Backend / orchestrateur"
          status={toStatus(runtimeTrace?.runtime.running)}
          details={[
            `Mode: ${runtimeTrace?.mode ?? 'Non disponible'}`,
            `Uptime: ${formatUptime(runtimeTrace?.runtime.uptime_seconds)}`,
            `Strategies chargees: ${runtimeTrace?.strategies.active_count ?? 'Non disponible'}`,
          ]}
        />
        <ServiceCard
          icon={<Wifi className="w-6 h-6" />}
          title="Flux marche Kraken"
          status={toStatus(runtimeTrace?.runtime.websocket_connected)}
          details={[
            runtimeTrace?.runtime.websocket_connected ? 'WebSocket connecte' : 'WebSocket non confirme',
            `Dernier tick: ${formatDate(typeof runtimeTrace?.trace.last_market_tick?.timestamp === 'string' ? runtimeTrace.trace.last_market_tick.timestamp : null)}`,
            `Paires: ${runtimeTrace?.strategies.pairs_watched.join(', ') || 'Non disponible'}`,
          ]}
        />
        <ServiceCard
          icon={<Database className="w-6 h-6" />}
          title="Bases de donnees"
          status={runtimeTrace?.database.state.accessible ? (runtimeTrace.paper_mode && !runtimeTrace.database.paper.accessible ? 'warning' : 'healthy') : 'critical'}
          details={[
            `State DB: ${runtimeTrace?.database.state.status ?? 'Non disponible'}`,
            `Paper DB: ${runtimeTrace?.database.paper.status ?? 'Non disponible'}`,
            `Trade ledger: ${runtimeTrace?.database.state.tables?.trade_ledger?.rows ?? 'Non disponible'} lignes`,
          ]}
        />
        <ServiceCard
          icon={<Terminal className="w-6 h-6" />}
          title="Executor / ordres"
          status={runtimeTrace?.order_executor.class_name ? (runtimeTrace.order_executor.recorded_trades_count > 0 ? 'healthy' : 'warning') : 'critical'}
          details={[
            `Executor: ${runtimeTrace?.order_executor.class_name ?? 'Non disponible'}`,
            `Ordres ouverts: ${runtimeTrace?.order_executor.open_orders_count ?? 'Non disponible'}`,
            `Trades enregistres: ${runtimeTrace?.order_executor.recorded_trades_count ?? 'Non disponible'}`,
          ]}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8 mb-6 lg:mb-8">
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-6">
          <h3 className="flex items-center gap-3 text-lg font-bold text-white mb-4">
            <ListChecks className="w-5 h-5 text-emerald-400" />
            Verification operationnelle
          </h3>
          <div className="space-y-2">
            {runtimeTrace?.checks.map((check) => (
              <div key={check.name} className="flex items-center justify-between p-3 bg-gray-700/30 rounded-xl">
                <div className="flex items-center gap-2">
                  {check.ok ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : <XCircle className="w-4 h-4 text-red-400" />}
                  <span className="text-white">{check.name}</span>
                </div>
                <span className={check.ok ? 'text-emerald-400 text-sm' : 'text-red-400 text-sm'}>{check.status}</span>
              </div>
            )) ?? <div className="text-gray-500">Trace runtime non disponible.</div>}
          </div>
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-6">
          <h3 className="flex items-center gap-3 text-lg font-bold text-white mb-4">
            <AlertTriangle className="w-5 h-5 text-amber-300" />
            Etat interprete
          </h3>
          <div className="space-y-3">
            {failedChecks.length > 0 ? failedChecks.map((issue) => (
              <div key={issue.name} className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-300">
                {issue.name}: {issue.status}
              </div>
            )) : (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-300">
                Aucun blocage critique verifie par les endpoints disponibles.
              </div>
            )}
            {recommendations.map((rec) => (
              <div key={rec} className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl text-blue-300">
                {rec}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8 mb-6 lg:mb-8">
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-6">
          <h3 className="flex items-center gap-3 text-lg font-bold text-white mb-4">
            <Clock className="w-5 h-5 text-emerald-400" />
            Traçabilite runtime
          </h3>
          <div className="space-y-3">
            <TraceRow label="Dernier tick marche" event={runtimeTrace?.trace.last_market_tick} />
            <TraceRow label="Dernier signal" event={runtimeTrace?.trace.last_signal} />
            <TraceRow label="Derniere decision" event={runtimeTrace?.trace.last_decision} />
            <TraceRow label="Dernier ordre" event={runtimeTrace?.trace.last_order} />
            <TraceRow label="Dernier trade execute" event={runtimeTrace?.trace.last_trade} />
            <TraceRow label="Derniere erreur" event={runtimeTrace?.trace.last_error} />
          </div>
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-6">
          <h3 className="flex items-center gap-3 text-lg font-bold text-white mb-4">
            <Wallet className="w-5 h-5 text-emerald-400" />
            Mode et capital backend
          </h3>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between gap-4 p-3 bg-gray-700/30 rounded-xl">
              <span className="text-gray-400">Mode</span>
              <span className="text-white font-bold">{runtimeTrace?.paper_mode ? 'Paper Trading' : 'Live Trading'}</span>
            </div>
            <div className="flex justify-between gap-4 p-3 bg-gray-700/30 rounded-xl">
              <span className="text-gray-400">Source capital</span>
              <span className="text-white font-bold">{runtimeTrace?.capital?.source ?? 'Non disponible'} / {runtimeTrace?.capital?.source_status ?? 'Non disponible'}</span>
            </div>
            <div className="flex justify-between gap-4 p-3 bg-gray-700/30 rounded-xl">
              <span className="text-gray-400">Capital total</span>
              <span className="text-white font-bold">{formatCurrency(runtimeTrace?.capital?.total_capital)}</span>
            </div>
            <div className="flex justify-between gap-4 p-3 bg-gray-700/30 rounded-xl">
              <span className="text-gray-400">Cash disponible</span>
              <span className="text-white font-bold">{formatCurrency(runtimeTrace?.capital?.available_cash)}</span>
            </div>
            <div className="flex justify-between gap-4 p-3 bg-gray-700/30 rounded-xl">
              <span className="text-gray-400">Warm-up / blocages</span>
              <span className="text-white font-bold">{runtimeTrace?.strategies.warmup_or_blocked.length ?? 'Non disponible'}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 mb-6 lg:mb-8 shadow-2xl">
        <h2 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">
          Historique ressources
        </h2>
        <div className="h-64 lg:h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="time" stroke="#9CA3AF" fontSize={12} />
              <YAxis stroke="#9CA3AF" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1F2937',
                  border: '1px solid #374151',
                  borderRadius: '12px',
                }}
              />
              <Line type="monotone" dataKey="ram" stroke="#3b82f6" strokeWidth={3} name="RAM %" dot={false} />
              <Line type="monotone" dataKey="cpu" stroke="#a855f7" strokeWidth={3} name="CPU %" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default Diagnostic;
