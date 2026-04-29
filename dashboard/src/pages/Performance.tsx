import React, { useState, useEffect, useCallback } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import MetricCard from '../components/ui/MetricCard';
import Tabs, { Tab } from '../components/ui/Tabs';
import { Activity, TrendingUp, BarChart3, Wallet, Target, Layers, GraduationCap, RefreshCw, AlertTriangle, CheckCircle, XCircle, Wifi, WifiOff, Clock } from 'lucide-react';
import { apiFetch } from '../api/client';


interface GlobalPerf {
  capital_total: number; capital_initial: number; profit_total: number;
  profit_percent: number; profit_factor: number; win_rate: number;
  total_trades: number; instances_count: number;
  by_strategy: { strategy: string; instances_count: number; capital_total: number; profit_total: number }[];
  history: { timestamp: string; capital: number; profit: number }[];
}
interface PairPerf {
  symbol: string; instances_count: number; capital_total: number;
  profit_total: number; profit_percent: number; profit_factor: number;
  win_rate: number; total_trades: number; max_drawdown: number; status: string;
  instances: {
    id: string; name: string; capital: number; profit: number; strategy: string; status: string;
    warmup?: { active?: boolean; blocked_reasons?: string[]; price_samples?: number; required_samples?: number };
    blocked_reasons?: string[];
  }[];
}
interface PaperPair {
  symbol: string; instance_count: number; total_trades: number;
  avg_profit_percent: number; avg_pf: number; win_rate: number;
  recommendation: string; warmup_active?: number; blocked_reasons?: string[];
}
interface PaperSummary { active_instances: number; live_instances: number; pairs_tested: number; is_paper_mode: boolean; by_pair: PaperPair[]; }
interface RebEvent { timestamp: string; instance_id: string; instance_name: string; action: string; amount: number; reason: string; }
interface RebStatus {
  enabled: boolean; check_count: number; last_check: string|null;
  total_reinvested: number; total_reduced: number;
  thresholds: { profit_threshold_pct: number; drawdown_threshold_pct: number; reinvest_pct: number; reduce_pct: number; };
  recent_events: RebEvent[];
}
interface BotStatus {
  running: boolean; instance_count: number; total_capital: number;
  total_profit: number; websocket_connected: boolean; uptime_seconds: number | null;
  total_trades?: number;
}
interface CapitalData {
  total_capital: number; available_cash: number; source: string; source_status?: string; paper_mode: boolean;
  autobot_trading_capital?: number | null; autobot_available_capital?: number | null;
  paper_historical_balance?: number | null; paper_unallocated_reserve?: number | null;
}
const formatUptime = (seconds: number | null): string => {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
};
const fmt = (n: number, d=2) => n.toLocaleString('fr-FR', {minimumFractionDigits:d, maximumFractionDigits:d});
const fmtEur = (n: number) => `${fmt(n)}€`;
const pfColor = (pf: number) => pf>=2?'text-emerald-400':pf>=1.5?'text-green-400':pf>=1?'text-yellow-400':'text-red-400';
const profitColor = (n: number) => n>=0?'text-emerald-400':'text-red-400';
const stratLabel = (s: string): string => {
  const m: Record<string,string> = {grid:'Grid Trading',trend:'Trend Following',breakout:'Breakout',dca:'DCA'};
  return m[s] || s;
};

async function apiFetchJson<T>(path: string): Promise<T|null> {
  try { 
    const r = await apiFetch(path); 
    return r.ok ? await r.json() : null; 
  } catch { 
    return null; 
  }
}

const RecBadge: React.FC<{rec:string}> = ({rec}) => {
  if (rec==='promote_to_live') return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"><CheckCircle className="w-3 h-3"/>Pret pour revue live</span>;
  if (rec==='stop') return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-red-500/20 text-red-400 border border-red-500/30"><XCircle className="w-3 h-3"/>Arrêter</span>;
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-blue-500/20 text-blue-400 border border-blue-500/30"><RefreshCw className="w-3 h-3"/>Continuer Paper</span>;
};
const Performance: React.FC = () => {
  const [activeTab, setActiveTab] = useState('global');
  const [isLoading, setIsLoading] = useState(true);
  const [globalPerf, setGlobalPerf] = useState<GlobalPerf|null>(null);
  const [pairPerfs, setPairPerfs] = useState<PairPerf[]>([]);
  const [paperSummary, setPaperSummary] = useState<PaperSummary|null>(null);
  const [rebStatus, setRebStatus] = useState<RebStatus|null>(null);
  const [botStatus, setBotStatus] = useState<BotStatus|null>(null);
  const [capitalData, setCapitalData] = useState<CapitalData|null>(null);
  const [expandedPair, setExpandedPair] = useState<string|null>(null);

  const tabs: Tab[] = [
    {id:'global',label:'Global',icon:<Activity className="w-4 h-4"/>},
    {id:'pairs',label:'Par Paire',icon:<Layers className="w-4 h-4"/>},
    {id:'training',label:'Entraînement',icon:<GraduationCap className="w-4 h-4"/>},
  ];

  const fetchAll = useCallback(async () => {
    const [g,p,pp,rb,bs,cap] = await Promise.all([
      apiFetchJson<GlobalPerf>('/api/performance/global'),
      apiFetchJson<{pairs:PairPerf[]}>('/api/performance/by-pair'),
      apiFetchJson<PaperSummary>('/api/paper-trading/summary'),
      apiFetchJson<RebStatus>('/api/rebalance/status'),
      apiFetchJson<BotStatus>('/api/status'),
      apiFetchJson<CapitalData>('/api/capital'),
    ]);
    if(g) setGlobalPerf(g); if(p) setPairPerfs(p.pairs);
    if(pp) setPaperSummary(pp); if(rb) setRebStatus(rb); if(bs) setBotStatus(bs);
    if(cap) setCapitalData(cap);
    setIsLoading(false);
  }, []);

  useEffect(() => { fetchAll(); const i=setInterval(fetchAll,15000); return ()=>clearInterval(i); }, [fetchAll]);

  if (isLoading) return (
    <div className="p-8 bg-gray-900 min-h-screen flex items-center justify-center">
      <div className="flex flex-col items-center">
        <div className="w-12 h-12 border-4 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin"/>
        <span className="mt-4 text-emerald-400">Chargement des performances...</span>
      </div>
    </div>
  );
  const renderGlobal = () => {
    if (!globalPerf) return (
      <div className="text-center py-12 text-gray-400">
        <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-yellow-500"/>
        <p>Impossible de charger les données. Vérifiez que le bot est actif.</p>
      </div>
    );
    const pos = globalPerf.profit_total >= 0;
    const activePaperCapital = capitalData?.autobot_trading_capital ?? globalPerf.capital_total;
    const activePaperAvailable = capitalData?.autobot_available_capital ?? capitalData?.available_cash;
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <MetricCard title={capitalData?.paper_mode ? 'Budget paper actif' : 'Capital Kraken/AUTOBOT'} value={fmtEur(capitalData?.paper_mode ? activePaperCapital : globalPerf.capital_total)} icon={<Wallet className="w-5 h-5"/>}/>
          <MetricCard title="Profit Total" value={`${pos?'+':''}${fmtEur(globalPerf.profit_total)}`} change={`${pos?'+':''}${fmt(globalPerf.profit_percent)}%`} isPositive={pos} icon={<TrendingUp className="w-5 h-5"/>}/>
          <MetricCard title="Profit Factor" value={fmt(globalPerf.profit_factor)} icon={<Target className="w-5 h-5"/>}/>
          <MetricCard title="Win Rate" value={`${fmt(globalPerf.win_rate,1)}%`} icon={<BarChart3 className="w-5 h-5"/>}/>
          <MetricCard title="Strategies actives" value={String(globalPerf.instances_count)} change={`${globalPerf.total_trades} trades`} icon={<Activity className="w-5 h-5"/>}/>
        </div>
        {globalPerf.history.length > 1 && (
          <div className="bg-gray-800 rounded-2xl p-6 border border-gray-700/50">
            <h3 className="text-xl font-bold text-emerald-400 mb-4">📊 Évolution du Capital</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={globalPerf.history}>
                  <defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/><stop offset="95%" stopColor="#10B981" stopOpacity={0}/></linearGradient></defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151"/>
                  <XAxis dataKey="timestamp" stroke="#9CA3AF" tickFormatter={t=>new Date(t).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}/>
                  <YAxis stroke="#9CA3AF" tickFormatter={v=>`${v}€`}/>
                  <Tooltip contentStyle={{backgroundColor:'#1F2937',border:'1px solid #10B981',borderRadius:'8px'}} formatter={(v:number)=>[`${fmt(v)}€`,'Capital']}/>
                  <Area type="monotone" dataKey="capital" stroke="#10B981" strokeWidth={2} fill="url(#cg)"/>
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
        {globalPerf.by_strategy.length > 0 && (
          <div className="bg-gray-800 rounded-2xl p-6 border border-gray-700/50">
            <h3 className="text-xl font-bold text-emerald-400 mb-4">📉 Par Stratégie</h3>
            <div className="space-y-3">
              {globalPerf.by_strategy.map(s=>(
                <div key={s.strategy} className="flex items-center justify-between p-4 bg-gray-700/30 rounded-xl border border-gray-600/30">
                  <div className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full ${s.profit_total>=0?'bg-emerald-400':'bg-red-400'}`}/>
                    <span className="text-white font-medium">{stratLabel(s.strategy)}</span>
                    <span className="text-gray-400 text-sm">{s.instances_count} strategie{s.instances_count>1?'s':''}</span>
                  </div>
                  <span className={`font-bold ${profitColor(s.profit_total)}`}>{s.profit_total>=0?'+':''}{fmtEur(s.profit_total)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {rebStatus && rebStatus.enabled && (
          <div className="bg-gray-800 rounded-2xl p-6 border border-gray-700/50">
            <h3 className="text-xl font-bold text-emerald-400 mb-4">⚖️ Auto-Rebalancement</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="p-3 bg-gray-700/30 rounded-lg"><p className="text-gray-400 text-xs">Vérifications</p><p className="text-white font-bold text-lg">{rebStatus.check_count}</p></div>
              <div className="p-3 bg-gray-700/30 rounded-lg"><p className="text-gray-400 text-xs">Réinvesti</p><p className="text-emerald-400 font-bold text-lg">{fmtEur(rebStatus.total_reinvested)}</p></div>
              <div className="p-3 bg-gray-700/30 rounded-lg"><p className="text-gray-400 text-xs">Réduit</p><p className="text-red-400 font-bold text-lg">{fmtEur(rebStatus.total_reduced)}</p></div>
              <div className="p-3 bg-gray-700/30 rounded-lg"><p className="text-gray-400 text-xs">Seuil Profit</p><p className="text-white font-bold text-lg">{rebStatus.thresholds.profit_threshold_pct}%</p></div>
            </div>
            {rebStatus.recent_events.length > 0 && (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {rebStatus.recent_events.map((e,i)=>(
                  <div key={i} className="flex items-center justify-between p-2 bg-gray-700/20 rounded-lg text-sm">
                    <span className={e.action==='reinvest'?'text-emerald-400':'text-red-400'}>{e.action==='reinvest'?'💰':'⚠️'} {e.instance_name} — {e.reason}</span>
                    <span className={`font-bold ${e.action==='reinvest'?'text-emerald-400':'text-red-400'}`}>{e.action==='reinvest'?'+':'-'}{fmt(e.amount)}€</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };
  const renderPairs = () => {
    if (!pairPerfs.length) return (
      <div className="text-center py-12 text-gray-400">
        <Layers className="w-12 h-12 mx-auto mb-4 text-gray-600"/>
        <p>Aucune paire de trading active.</p>
      </div>
    );
    return (
      <div className="space-y-4">
        {pairPerfs.map(pair=>(
          <div key={pair.symbol} className="bg-gray-800 rounded-2xl border border-gray-700/50 overflow-hidden">
            <div className="p-5 cursor-pointer hover:bg-gray-700/30 transition-colors" onClick={()=>setExpandedPair(expandedPair===pair.symbol?null:pair.symbol)}>
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div className="flex items-center gap-4">
                  <span className="text-lg font-bold text-white">{pair.symbol}</span>
                  <span className="text-gray-400 text-sm">{pair.instances_count} strategie{pair.instances_count>1?'s':''}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${pair.status==='live'?'bg-emerald-500/20 text-emerald-400':'bg-blue-500/20 text-blue-400'}`}>{pair.status}</span>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <p className="text-gray-400 text-xs">Profit</p>
                    <p className={`font-bold ${profitColor(pair.profit_total)}`}>{pair.profit_total>=0?'+':''}{fmtEur(pair.profit_total)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-gray-400 text-xs">PF</p>
                    <p className={`font-bold ${pfColor(pair.profit_factor)}`}>{fmt(pair.profit_factor)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-gray-400 text-xs">Win Rate</p>
                    <p className="text-white font-bold">{fmt(pair.win_rate,1)}%</p>
                  </div>
                  <div className="text-right">
                    <p className="text-gray-400 text-xs">Trades</p>
                    <p className="text-white font-bold">{pair.total_trades}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-gray-400 text-xs">Max DD</p>
                    <p className="text-red-400 font-bold">{fmt(pair.max_drawdown,1)}%</p>
                  </div>
                  <span className={`text-gray-400 transition-transform ${expandedPair===pair.symbol?'rotate-180':''}`}>{"▼"}</span>
                </div>
              </div>
            </div>
            {expandedPair===pair.symbol && pair.instances.length > 0 && (
              <div className="border-t border-gray-700/50 p-4 bg-gray-850">
                <h4 className="text-sm font-bold text-gray-400 mb-3">Strategies sur {pair.symbol}</h4>
                <div className="space-y-2">
                  {pair.instances.map(inst=>(
                    <div key={inst.id} className="flex items-center justify-between p-3 bg-gray-700/20 rounded-lg">
                      <div>
                        <span className="text-white font-medium">{inst.name}</span>
                        <span className="text-gray-400 text-sm ml-2">({inst.strategy})</span>
                        {inst.warmup?.active && (
                          <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                            <Clock className="w-3 h-3"/>
                            Chauffe {inst.warmup.price_samples ?? 0}/{inst.warmup.required_samples ?? 14}
                          </span>
                        )}
                        {!inst.warmup?.active && (
                          <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                            <CheckCircle className="w-3 h-3"/>
                            Prête
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-4">
                        <span className="text-gray-400 text-sm">{fmtEur(inst.capital)}</span>
                        <span className={`font-bold ${profitColor(inst.profit)}`}>{inst.profit>=0?'+':''}{fmtEur(inst.profit)}</span>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${inst.status==='running'?'bg-emerald-500/20 text-emerald-400':'bg-gray-500/20 text-gray-400'}`}>{inst.status}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };
  const renderTraining = () => {
    if (!paperSummary) return (
      <div className="text-center py-12 text-gray-400">
        <GraduationCap className="w-12 h-12 mx-auto mb-4 text-gray-600"/>
        <p>Données d'entraînement non disponibles.</p>
      </div>
    );
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <MetricCard title="Strategies paper actives" value={String(paperSummary.active_instances)} icon={<GraduationCap className="w-5 h-5"/>}/>
          <MetricCard title="Strategies live" value={String(paperSummary.live_instances)} icon={<Activity className="w-5 h-5"/>}/>
          <MetricCard title="Paires surveillees" value={String(paperSummary.pairs_tested)} icon={<Layers className="w-5 h-5"/>}/>
        </div>
        {paperSummary.by_pair.length > 0 && (
          <div className="bg-gray-800 rounded-2xl p-6 border border-gray-700/50">
            <h3 className="text-xl font-bold text-emerald-400 mb-4">Performance par paire</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Paire</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Strategies</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Trades</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Profit Moy.</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">PF Moy.</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Win Rate</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Recommandation</th>
                  </tr>
                </thead>
                <tbody>
                  {paperSummary.by_pair.map(p=>(
                    <tr key={p.symbol} className="border-b border-gray-700/50 hover:bg-gray-700/20">
                      <td className="py-3 px-4 text-white font-medium">{p.symbol}</td>
                      <td className="py-3 px-4 text-right text-gray-300">{p.instance_count}</td>
                      <td className="py-3 px-4 text-right text-gray-300">{p.total_trades}</td>
                      <td className={`py-3 px-4 text-right font-bold ${profitColor(p.avg_profit_percent)}`}>{p.avg_profit_percent>=0?'+':''}{fmt(p.avg_profit_percent)}%</td>
                      <td className={`py-3 px-4 text-right font-bold ${pfColor(p.avg_pf)}`}>{fmt(p.avg_pf)}</td>
                      <td className="py-3 px-4 text-right text-gray-300">{fmt(p.win_rate,1)}%</td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex flex-col items-end gap-1">
                          <RecBadge rec={p.recommendation}/>
                          {p.warmup_active ? <span className="text-amber-300 text-xs">Chauffe: {p.warmup_active}</span> : null}
                          {p.blocked_reasons?.length ? <span className="text-gray-400 text-xs">{p.blocked_reasons.join(', ')}</span> : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex items-center space-x-3 mb-3">
          <TrendingUp className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400"/>
          <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">Performance</h1>
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">Vue operationnelle issue du backend AUTOBOT. Les champs indisponibles restent explicites.</p>
      </div>


      {/* Paper Trading Banner */}
      {paperSummary && paperSummary.is_paper_mode && (
        <div className="mb-6 bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 flex items-start gap-3">
          <span className="text-2xl">🎓</span>
          <div>
            <h3 className="text-amber-400 font-bold text-lg">Mode Entraînement (Paper Trading)</h3>
            <p className="text-amber-300/80 text-sm">Le bot s'entraîne avec du capital virtuel. Aucun argent réel n'est engagé.</p>
            <div className="flex gap-4 mt-2 text-sm">
              <span className="text-gray-400">Source : <strong className="text-white">{capitalData?.source ?? 'backend'}</strong></span>
              <span className="text-gray-400">Statut source : <strong className="text-white">{capitalData?.source_status ?? 'inconnu'}</strong></span>
              <span className="text-gray-400">Cash disponible : <strong className="text-amber-400">{capitalData ? fmtEur(capitalData.available_cash) : '—'}</strong></span>
              <span className="text-gray-400">Capital paper : <strong className="text-amber-400">{capitalData ? fmtEur(capitalData.total_capital) : (globalPerf ? fmtEur(globalPerf.capital_total) : '—')}</strong></span>
            </div>
          </div>
        </div>
      )}
      {paperSummary && !paperSummary.is_paper_mode && (
        <div className="mb-6 bg-emerald-500/10 border border-emerald-500/30 rounded-2xl p-4 flex items-start gap-3">
          <span className="text-2xl">🚀</span>
          <div>
            <h3 className="text-emerald-400 font-bold text-lg">Mode Live Trading</h3>
            <p className="text-emerald-300/80 text-sm">Le bot trade avec du capital réel sur Kraken.</p>
          </div>
        </div>
      )}

      {/* Bot Status */}
      {botStatus && (
        <div className="mb-6 bg-gray-800 border border-gray-700/50 rounded-2xl p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              {botStatus.running ? (
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                </span>
              ) : (
                <span className="h-3 w-3 rounded-full bg-red-500"></span>
              )}
              <span className={`font-bold ${botStatus.running ? 'text-emerald-400' : 'text-red-400'}`}>
                {botStatus.running ? `Bot Actif - ${capitalData?.paper_mode ? 'Paper Trading' : 'Live Trading'}` : 'Bot Deconnecte'}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm text-gray-400">
              <span className="flex items-center gap-1">
                {botStatus.websocket_connected ? <Wifi className="w-4 h-4 text-emerald-400"/> : <WifiOff className="w-4 h-4 text-red-400"/>}
                {botStatus.websocket_connected ? <span className="text-emerald-400 ml-1">Connecté</span> : <span className="text-red-400 ml-1">Déconnecté</span>}
              </span>
              <span>Strategies : <strong className="text-white">{botStatus.instance_count}</strong></span>
              <span className="flex items-center gap-1"><Clock className="w-4 h-4"/> Uptime : <strong className="text-white">{formatUptime(botStatus.uptime_seconds)}</strong></span>
            </div>
          </div>
        </div>
      )}

      <div className="mb-6">
        <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab}/>
      </div>

      {activeTab === 'global' && renderGlobal()}
      {activeTab === 'pairs' && renderPairs()}
      {activeTab === 'training' && renderTraining()}
    </div>
  );
};

export default Performance;
