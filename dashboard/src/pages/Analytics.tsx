import React, { useState, useEffect } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import MetricCard from '../components/ui/MetricCard';
import { PieChart, Target, TrendingUp, Shield, BarChart3 } from 'lucide-react';
import { calculateRendementPercent } from './analyticsMetrics';
import { apiFetch } from '../api/client';



interface ScalingStatusResponse {
  enabled: boolean;
  message?: string | null;
  guard: { state: string; reasons: string[] };
  activation: { action: string; target_instances: number; target_tier: number; reason: string };
}

interface UniverseStatusResponse {
  enabled: boolean;
  message?: string | null;
  counts: { supported: number; eligible: number; ranked: number; websocket_active: number; actively_traded: number; };
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

interface PortfolioAllocationResponse {
  enabled: boolean;
  message?: string | null;
  allocation: null | { total_allocated: number; reserve_cash: number; risk_budget_remaining: number; explain: Record<string, number> };
}


interface ScalingStatusResponse {
  enabled: boolean;
  message?: string | null;
  guard: { state: string; reasons: string[] };
  activation: { action: string; target_instances: number; target_tier: number; reason: string };
}

interface UniverseStatusResponse {
  enabled: boolean;
  message?: string | null;
  counts: { supported: number; eligible: number; ranked: number; websocket_active: number; actively_traded: number; };
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

interface PortfolioAllocationResponse {
  enabled: boolean;
  message?: string | null;
  allocation: null | { total_allocated: number; reserve_cash: number; risk_budget_remaining: number; explain: Record<string, number> };
}

const Analytics: React.FC = () => {
  type PerfPoint = { date: string; portfolio: number };

  const [performanceData, setPerformanceData] = useState<PerfPoint[]>([]);
  const [metrics, setMetrics] = useState({
    rendement: '—',
    sharpe: '—',
    winRate: '—',
    volatility: '—',
    maxDrawdown: '—'
  });
  const [isLoading, setIsLoading] = useState(true);
  const [scalingStatus, setScalingStatus] = useState<ScalingStatusResponse | null>(null);
  const [universeStatus, setUniverseStatus] = useState<UniverseStatusResponse | null>(null);
  const [opportunities, setOpportunities] = useState<OpportunitiesResponse | null>(null);
  const [portfolioAllocation, setPortfolioAllocation] = useState<PortfolioAllocationResponse | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const capitalRes = await apiFetch(`/api/capital`);
        if (capitalRes.ok) {
          const capitalData = await capitalRes.json();
          const pnlPercent = calculateRendementPercent(capitalData, '0.0');
          
          setMetrics(prev => ({
            ...prev,
            rendement: `${pnlPercent}%`,
          }));
        }

        const historyRes = await apiFetch(`/api/history?days=7`);
        if (historyRes.ok) {
          const historyData = await historyRes.json();
          if (historyData.history && historyData.history.length > 0) {
            setPerformanceData(historyData.history.map((item: { timestamp: string; value: number }) => ({
              date: new Date(item.timestamp).toLocaleDateString('fr-FR'),
              portfolio: item.value,
            })));
          }
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
      } catch {
        setIsLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

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

  return (
    <div className="p-8 bg-gray-900 min-h-screen">
      <div className="mb-8">
        <div className="flex items-center space-x-3 mb-3">
          <PieChart className="w-8 h-8 text-emerald-400" />
          <h1 className="text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
            Analytics
          </h1>
        </div>
        <p className="text-gray-400">Metriques de performance en temps reel.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <MetricCard title="Rendement" value={metrics.rendement} icon={<TrendingUp className="w-5 h-5" />} />
        <MetricCard title="Sharpe" value={metrics.sharpe} icon={<Target className="w-5 h-5" />} />
        <MetricCard title="Win Rate" value={metrics.winRate} icon={<BarChart3 className="w-5 h-5" />} />
      </div>

      <div className="bg-gray-800 rounded-2xl p-8 mb-8">
        <h3 className="text-2xl font-bold text-emerald-400 mb-6">Performance</h3>
        {performanceData.length > 0 ? (
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={performanceData}>
                <defs>
                  <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="date" stroke="#9CA3AF" />
                <YAxis stroke="#9CA3AF" />
                <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #10B981' }} />
                <Area type="monotone" dataKey="portfolio" stroke="#10B981" strokeWidth={3} fill="url(#portfolioGradient)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-gray-500 text-center py-8">
            Pas encore d historique. Les donnees apparaitront apres quelques heures de trading.
          </div>
        )}
      </div>


      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-8">
        <div className="bg-gray-800 rounded-2xl p-6">
          <h3 className="text-xl font-bold text-emerald-400 mb-4">Scaling & Guard</h3>
          {scalingStatus?.enabled ? (
            <div className="space-y-2 text-sm">
              <div className="text-gray-300">Tier: <span className="text-white">{scalingStatus.activation.target_tier}</span></div>
              <div className="text-gray-300">Action: <span className="text-emerald-400">{scalingStatus.activation.action}</span></div>
              <div className="text-gray-300">Guard: <span className="text-yellow-400">{scalingStatus.guard.state}</span></div>
              <div className="text-gray-400">Raisons: {(scalingStatus.guard.reasons || []).join(', ') || '—'}</div>
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Feature disabled by configuration</div>
          )}
        </div>

        <div className="bg-gray-800 rounded-2xl p-6">
          <h3 className="text-xl font-bold text-emerald-400 mb-4">Universe & Allocation</h3>
          {universeStatus?.enabled ? (
            <div className="space-y-2 text-sm">
              <div className="text-gray-300">Supported / Eligible / Ranked: <span className="text-white">{universeStatus.counts.supported} / {universeStatus.counts.eligible} / {universeStatus.counts.ranked}</span></div>
              <div className="text-gray-300">WS active / traded: <span className="text-white">{universeStatus.counts.websocket_active} / {universeStatus.counts.actively_traded}</span></div>
              {portfolioAllocation?.enabled && portfolioAllocation.allocation ? (
                <>
                  <div className="text-gray-300">Allocated: <span className="text-white">{portfolioAllocation.allocation.total_allocated.toFixed(2)}€</span></div>
                  <div className="text-gray-300">Reserve cash: <span className="text-white">{portfolioAllocation.allocation.reserve_cash.toFixed(2)}€</span></div>
                </>
              ) : <div className="text-gray-500">Feature disabled by configuration</div>}
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Feature disabled by configuration</div>
          )}
        </div>
      </div>

      <div className="bg-gray-800 rounded-2xl p-6 mb-8">
        <h3 className="text-xl font-bold text-emerald-400 mb-4">Opportunites runtime</h3>
        {opportunities ? (
          <div className="space-y-2 text-sm">
            <div className="flex flex-wrap justify-between gap-2 border-b border-gray-700 pb-3 text-xs text-gray-400">
              <span>Mode: {opportunities.execution_gate?.mode || 'paper'}</span>
              <span>{opportunities.selected_symbols?.length ? `Selection: ${opportunities.selected_symbols.join(', ')}` : 'Aucune paire selectionnee'}</span>
            </div>
            {opportunities.opportunities.slice(0, 6).map((op, idx) => (
              <div key={`${op.symbol}-${idx}`} className="border-b border-gray-700 pb-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-white font-semibold">{op.symbol}</span>
                  <span className={op.status === 'tradable' ? 'text-emerald-400 font-semibold' : 'text-yellow-400 font-semibold'}>
                    {op.status === 'tradable' ? 'tradable' : 'non tradable'}
                  </span>
                </div>
                <div className="mt-1 text-xs text-gray-400">{op.reason || 'En attente de signal'}</div>
                <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  <span className="text-gray-300">Score <span className="text-white">{op.score.toFixed(1)}</span></span>
                  <span className="text-gray-300">Gross <span className="text-white">{(op.gross_edge_bps ?? 0).toFixed(1)} bps</span></span>
                  <span className="text-gray-300">Net <span className="text-white">{(op.net_edge_bps ?? 0).toFixed(1)} bps</span></span>
                  <span className="text-gray-300">ATR <span className="text-white">{(op.atr_bps ?? 0).toFixed(1)} bps</span></span>
                </div>
              </div>
            ))}
            {opportunities.opportunities.length === 0 && <div className="text-gray-500">Aucune opportunité classée.</div>}
          </div>
        ) : (
          <div className="text-gray-500 text-sm">Opportunites indisponibles</div>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        <div className="bg-gray-800 rounded-2xl p-8">
          <h3 className="text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
            <Shield className="w-6 h-6" />
            <span>Metriques de Risque</span>
          </h3>
          <div className="space-y-4">
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Volatilite</span>
              <span className="font-bold text-blue-400">{metrics.volatility}</span>
            </div>
            <div className="flex justify-between py-2 border-b border-gray-700">
              <span className="text-gray-400">Max Drawdown</span>
              <span className="font-bold text-red-400">{metrics.maxDrawdown}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Analytics;
