import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import MetricCard from '../components/ui/MetricCard';
import LiveLog from '../components/ui/LiveLog';
import { TrendingUp, DollarSign, Target, Activity } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { apiFetch } from '../api/client';


// CORRECTION: Types pour les données API
interface InstanceStatus {
  id: string;
  name: string;
  capital: number;
  profit: number;
  status: string;
  strategy: string;
  open_positions: number;
}

interface GlobalStatus {
  running: boolean;
  instance_count: number;
  total_capital: number;
  total_profit: number;
  websocket_connected: boolean;
  uptime_seconds: number | null;
}

interface PositionInfo {
  pair: string;
  side: string;
  size: string;
  entry_price: number;
  current_price: number;
  pnl: number;
  pnl_percent: number;
}


interface ScalingStatusResponse {
  enabled: boolean;
  message?: string | null;
  guard: { state: string; reasons: string[] };
  activation: { action: string; target_instances: number; target_tier: number; reason: string };
  explanation: { decision: string; reason: string; guard_state: string; guard_reasons: string[] };
}

interface UniverseStatusResponse {
  enabled: boolean;
  message?: string | null;
  counts: {
    supported: number;
    eligible: number;
    ranked: number;
    websocket_active: number;
    actively_traded: number;
  };
}

interface OpportunitiesResponse {
  enabled?: boolean;
  message?: string | null;
  selected_symbols?: string[];
  execution_gate?: { mode?: string; selection_applies_to_execution?: boolean };
  opportunities: Array<{
    symbol: string;
    score: number;
    status?: string;
    reason?: string;
    gross_edge_bps?: number;
    cost_bps?: number;
    net_edge_bps?: number;
    atr_bps?: number;
    spread_bps?: number;
    blockers?: string[];
    explain?: Record<string, unknown>;
  }>;
}

interface HistoryPoint {
  timestamp: string;
  value: number;
}

interface PortfolioAllocationResponse {
  enabled: boolean;
  message?: string | null;
  allocation: null | {
    symbol_caps: Record<string, number>;
    total_allocated: number;
    reserve_cash: number;
    risk_budget_remaining: number;
    reasons: Record<string, string>;
    explain: Record<string, number>;
  };
}


const LiveTrading: React.FC = () => {
  const { capitalTotal, setCapitalTotal, botStatus, setBotStatus } = useAppStore();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // CORRECTION: États pour les données réelles de l'API
  const [globalStatus, setGlobalStatus] = useState<GlobalStatus | null>(null);
  const [positions, setPositions] = useState<PositionInfo[]>([]);
  const [portfolioData, setPortfolioData] = useState<Array<{ time: string; value: number }>>([]);
  const [scalingStatus, setScalingStatus] = useState<ScalingStatusResponse | null>(null);
  const [universeStatus, setUniverseStatus] = useState<UniverseStatusResponse | null>(null);
  const [opportunities, setOpportunities] = useState<OpportunitiesResponse | null>(null);
  const [portfolioAllocation, setPortfolioAllocation] = useState<PortfolioAllocationResponse | null>(null);

  // CORRECTION: Connexion au backend API
  useEffect(() => {
    const fetchData = async () => {
      try {
        setError(null);

        // Récupère le statut global
        const statusRes = await apiFetch(`/api/status`);
        if (!statusRes.ok) throw new Error(`API Error: ${statusRes.status}`);
        const statusData: GlobalStatus = await statusRes.json();
        setGlobalStatus(statusData);
        setCapitalTotal(statusData.total_capital);
        setBotStatus(statusData.running ? 'ACTIVE' : 'INACTIVE');

        // Récupère les instances
        const instancesRes = await apiFetch(`/api/instances`);
        if (!instancesRes.ok) throw new Error(`API Error: ${instancesRes.status}`);
        const instancesData: InstanceStatus[] = await instancesRes.json();

        // Récupère les positions de la première instance (s'il y en a une)
        if (instancesData.length > 0) {
          const firstInstanceId = instancesData[0].id;
          const positionsRes = await apiFetch(`/api/instances/${firstInstanceId}/positions`);
          if (positionsRes.ok) {
            const positionsData: PositionInfo[] = await positionsRes.json();
            setPositions(positionsData);
          } else {
            setPositions([]);
          }
        } else {
          setPositions([]);
        }

        const historyRes = await apiFetch(`/api/history?days=1`);
        if (historyRes.ok) {
          const historyData = await historyRes.json();
          const series: HistoryPoint[] = Array.isArray(historyData?.history) ? historyData.history : [];
          if (series.length > 0) {
            setPortfolioData(series.slice(-24).map((item) => ({
              time: new Date(item.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
              value: item.value,
            })));
          } else {
            setPortfolioData([{ time: 'Now', value: statusData.total_capital }]);
          }
        } else {
          setPortfolioData([{ time: 'Now', value: statusData.total_capital }]);
        }

        const [scalingRes, universeRes, opportunitiesRes, allocationRes] = await Promise.all([
          apiFetch(`/api/scaling/status`),
          apiFetch(`/api/universe/status`),
          apiFetch(`/api/opportunities`),
          apiFetch(`/api/portfolio/allocation`),
        ]);

        if (scalingRes.ok) setScalingStatus(await scalingRes.json());
        if (universeRes.ok) setUniverseStatus(await universeRes.json());
        if (opportunitiesRes.ok) setOpportunities(await opportunitiesRes.json());
        if (allocationRes.ok) setPortfolioAllocation(await allocationRes.json());

        setIsLoading(false);
      } catch (err) {
        console.error('Erreur connexion API:', err);
        setError(err instanceof Error ? err.message : 'Erreur de connexion au bot');
        setIsLoading(false);
      }
    };

    // Charge les données immédiatement
    fetchData();

    // CORRECTION: Rafraîchissement automatique toutes les 5 secondes
    const interval = setInterval(fetchData, 5000);

    return () => clearInterval(interval);
  }, [setCapitalTotal, setBotStatus]);

  // CORRECTION: Utilise le profit global de l'API (pas seulement 1ère instance)
  const totalPnl = globalStatus?.total_profit || 0;
  const pnlPercent = globalStatus?.total_capital && globalStatus.total_capital > 0
    ? (totalPnl / globalStatus.total_capital) * 100 
    : 0;

  
  if (isLoading) {
    return (
      <div className="p-8 bg-gray-900 min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center">
          <div className="w-12 h-12 border-4 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin"></div>
          <span className="mt-4 text-emerald-400">Chargement...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
        <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
          <div className="flex items-center space-x-3 mb-3">
            <TrendingUp className="w-6 lg:w-8 h-6 lg:h-8 text-red-400" />
            <h1 className="text-2xl lg:text-4xl font-bold text-red-400">
              Erreur de connexion
            </h1>
          </div>
          <p className="text-gray-400 text-sm lg:text-lg mb-4">
            Impossible de se connecter au bot de trading.
          </p>
          <div className="bg-red-500/20 border border-red-500/50 rounded-lg p-4 text-red-400">
            {error}
          </div>
          <p className="text-gray-500 mt-4 text-sm">
            Vérifiez que le bot est démarré: <code className="bg-gray-800 px-2 py-1 rounded">python src/autobot/v2/main_async.py</code>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      {/* Header */}
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center space-x-3">
            <TrendingUp className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400" />
            <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
              Live Trading
            </h1>
          </div>
          <div className={`px-3 py-1 rounded-full text-sm font-bold ${
            botStatus === 'ACTIVE' 
              ? 'bg-emerald-500/20 text-emerald-400' 
              : 'bg-red-500/20 text-red-400'
          }`}>
            {botStatus === 'ACTIVE' ? '● En cours' : '● Arrêté'}
          </div>
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">
          Performances en temps réel du robot de trading.
          {globalStatus?.websocket_connected && (
            <span className="text-emerald-400 ml-2">● WebSocket connecté</span>
          )}
        </p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <MetricCard 
          title="Capital Total" 
          value={capitalTotal.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })} 
          change={globalStatus ? `+${globalStatus.total_profit.toFixed(2)}€` : undefined}
          icon={<DollarSign className="w-5 h-5" />} 
        />
        <MetricCard 
          title="Profit/Perte Total" 
          value={`${totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}€`}
          change={`${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%`}
          icon={<TrendingUp className="w-5 h-5" />} 
        />
        <MetricCard 
          title="Instances Actives" 
          value={globalStatus?.instance_count.toString() || '0'}
          change={globalStatus ? `${globalStatus.instance_count} stratégie(s)` : undefined}
          icon={<Target className="w-5 h-5" />} 
        />
      </div>
      


      {/* Control Plane Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6 lg:mb-8">
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-6 shadow-2xl">
          <h3 className="text-lg lg:text-xl font-bold text-emerald-400 mb-3">Scaling Status</h3>
          {scalingStatus?.enabled ? (
            <div className="space-y-2 text-sm">
              <div className="text-gray-300">Tier cible: <span className="text-white font-semibold">{scalingStatus.activation.target_tier}</span></div>
              <div className="text-gray-300">Décision: <span className="text-emerald-400 font-semibold">{scalingStatus.activation.action}</span></div>
              <div className="text-gray-300">Guard: <span className="text-yellow-400 font-semibold">{scalingStatus.guard.state}</span></div>
              <div className="text-gray-400">Raisons: {(scalingStatus.guard.reasons || []).join(', ') || '—'}</div>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Feature disabled by configuration</div>
          )}
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-6 shadow-2xl">
          <h3 className="text-lg lg:text-xl font-bold text-emerald-400 mb-3">Universe Status</h3>
          {universeStatus?.enabled ? (
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="text-gray-300">Supported: <span className="text-white">{universeStatus.counts.supported}</span></div>
              <div className="text-gray-300">Eligible: <span className="text-white">{universeStatus.counts.eligible}</span></div>
              <div className="text-gray-300">Ranked: <span className="text-white">{universeStatus.counts.ranked}</span></div>
              <div className="text-gray-300">WS Active: <span className="text-white">{universeStatus.counts.websocket_active}</span></div>
              <div className="text-gray-300">Traded: <span className="text-white">{universeStatus.counts.actively_traded}</span></div>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Feature disabled by configuration</div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6 lg:mb-8">
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-6 shadow-2xl">
          <h3 className="text-lg lg:text-xl font-bold text-emerald-400 mb-3">Opportunites runtime</h3>
          {opportunities ? (
            <div className="space-y-2 max-h-56 overflow-auto">
              <div className="flex flex-wrap justify-between gap-2 border-b border-gray-700/40 pb-2 text-xs text-gray-400">
                <span>Mode: {opportunities.execution_gate?.mode || 'paper'}</span>
                <span>{opportunities.selected_symbols?.length ? `Selection: ${opportunities.selected_symbols.join(', ')}` : 'Aucune paire selectionnee'}</span>
              </div>
              {opportunities.opportunities.slice(0, 8).map((row, idx) => (
                <div key={`${row.symbol}-${idx}`} className="text-sm border-b border-gray-700/40 pb-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-white font-medium">{row.symbol}</span>
                    <span className={row.status === 'tradable' ? 'text-emerald-400 font-semibold' : 'text-yellow-400 font-semibold'}>
                      {row.status === 'tradable' ? 'tradable' : 'non tradable'}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-gray-400">{row.reason || 'En attente de signal'}</div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                    <span className="text-gray-300">Score <span className="text-white">{row.score.toFixed(1)}</span></span>
                    <span className="text-gray-300">Net <span className="text-white">{(row.net_edge_bps ?? 0).toFixed(1)} bps</span></span>
                    <span className="text-gray-300">Gross <span className="text-white">{(row.gross_edge_bps ?? 0).toFixed(1)} bps</span></span>
                    <span className="text-gray-300">ATR <span className="text-white">{(row.atr_bps ?? 0).toFixed(1)} bps</span></span>
                  </div>
                </div>
              ))}
              {opportunities.opportunities.length === 0 && <div className="text-gray-500 text-sm">Aucune opportunité classée.</div>}
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Opportunites indisponibles</div>
          )}
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-6 shadow-2xl">
          <h3 className="text-lg lg:text-xl font-bold text-emerald-400 mb-3">Portfolio Allocation</h3>
          {portfolioAllocation?.enabled && portfolioAllocation.allocation ? (
            <div className="space-y-2 text-sm">
              <div className="text-gray-300">Capital alloué: <span className="text-white">{portfolioAllocation.allocation.total_allocated.toFixed(2)}€</span></div>
              <div className="text-gray-300">Réserve cash: <span className="text-white">{portfolioAllocation.allocation.reserve_cash.toFixed(2)}€</span></div>
              <div className="text-gray-300">Risque restant: <span className="text-white">{portfolioAllocation.allocation.risk_budget_remaining.toFixed(2)}</span></div>
              <div className="text-gray-400 text-xs">Why hold/expand/reduce: {(scalingStatus?.explanation?.reason) || '—'}</div>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Feature disabled by configuration</div>
          )}
        </div>
      </div>

      {/* Portfolio Evolution Chart */}
      <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 mb-6 lg:mb-8 shadow-2xl">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6">
          <h2 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-2 sm:mb-0">
            Évolution du Portefeuille
          </h2>
          <div className="text-left sm:text-right">
            <div className="text-2xl lg:text-3xl font-bold text-white">
              {capitalTotal.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })}
            </div>
            <div className={`text-sm ${totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}€ ({pnlPercent >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%)
            </div>
          </div>
        </div>
        <div className="h-64 lg:h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={portfolioData}>
              <defs><linearGradient id="colorGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/><stop offset="95%" stopColor="#10B981" stopOpacity={0}/></linearGradient></defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="time" stroke="#9CA3AF" fontSize={12} />
              <YAxis stroke="#9CA3AF" fontSize={12} domain={['dataMin - 100', 'dataMax + 100']} />
              <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #10B981', borderRadius: '12px' }} />
              <Line type="monotone" dataKey="value" stroke="#10B981" strokeWidth={3} dot={false} fill="url(#colorGradient)" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8">
        {/* Positions Ouvertes */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
            <Activity className="w-5 lg:w-6 h-5 lg:h-6" />
            <span>Positions Ouvertes</span>
            <span className="text-sm bg-emerald-500/20 text-emerald-400 px-2 py-1 rounded-lg font-normal">{positions.length} active{positions.length > 1 ? 's' : ''}</span>
          </h3>
          {positions.length === 0 ? (
            <div className="text-gray-500 text-center py-8">
              Aucune position ouverte
            </div>
          ) : (
            <div className="space-y-3">
              {positions.map((position, index) => (
                <div key={index} className="p-4 bg-gray-700/50 rounded-xl border border-gray-600/30">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex items-center space-x-3">
                      <span className="text-white font-bold">{position.pair}</span>
                      <span className={`px-2 py-1 rounded text-xs font-bold ${position.side === 'LONG' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-blue-500/20 text-blue-400'}`}>
                        {position.side}
                      </span>
                    </div>
                    <div className="text-right">
                      <div className={`font-bold ${position.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {position.pnl >= 0 ? '+' : ''}{position.pnl.toFixed(2)}€
                      </div>
                      <div className={`text-sm ${position.pnl_percent >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {position.pnl_percent >= 0 ? '+' : ''}{position.pnl_percent.toFixed(2)}%
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div><span className="text-gray-400">Taille: </span><span className="text-white">{position.size}</span></div>
                    <div><span className="text-gray-400">Entrée: </span><span className="text-white">{position.entry_price.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })}</span></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Journal d'Activité */}
        <LiveLog />
      </div>
    </div>
  );
};

export default LiveTrading;
