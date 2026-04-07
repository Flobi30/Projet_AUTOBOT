import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import MetricCard from '../components/ui/MetricCard';
import LiveLog from '../components/ui/LiveLog';
import { TrendingUp, DollarSign, Target, AlertTriangle, Activity } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import Skeleton from 'react-loading-skeleton';
import 'react-loading-skeleton/dist/skeleton.css';

const API_BASE_URL = 'http://204.168.205.73:8080';
const API_TOKEN = 'autobot_token_12345';
const authHeaders = { 'Authorization': `Bearer ${API_TOKEN}` };

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

const SkeletonGrid = () => (
  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
    <Skeleton height={120} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
    <Skeleton height={120} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
    <Skeleton height={120} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
  </div>
);

const LiveTrading: React.FC = () => {
  const { capitalTotal, setCapitalTotal, botStatus, setBotStatus } = useAppStore();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // CORRECTION: États pour les données réelles de l'API
  const [globalStatus, setGlobalStatus] = useState<GlobalStatus | null>(null);
  const [instances, setInstances] = useState<InstanceStatus[]>([]);
  const [positions, setPositions] = useState<PositionInfo[]>([]);

  // CORRECTION: Connexion au backend API
  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        setError(null);

        // Récupère le statut global
        const statusRes = await fetch(`${API_BASE_URL}/api/status`, { headers: authHeaders });
        if (!statusRes.ok) throw new Error(`API Error: ${statusRes.status}`);
        const statusData: GlobalStatus = await statusRes.json();
        setGlobalStatus(statusData);
        setCapitalTotal(statusData.total_capital);
        setBotStatus(statusData.running ? 'ACTIVE' : 'INACTIVE');

        // Récupère les instances
        const instancesRes = await fetch(`${API_BASE_URL}/api/instances`, { headers: authHeaders });
        if (!instancesRes.ok) throw new Error(`API Error: ${instancesRes.status}`);
        const instancesData: InstanceStatus[] = await instancesRes.json();
        setInstances(instancesData);

        // Récupère les positions de la première instance (s'il y en a une)
        if (instancesData.length > 0) {
          const firstInstanceId = instancesData[0].id;
          const positionsRes = await fetch(`${API_BASE_URL}/api/instances/${firstInstanceId}/positions`, { headers: authHeaders });
          if (positionsRes.ok) {
            const positionsData: PositionInfo[] = await positionsRes.json();
            setPositions(positionsData);
          }
        }

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

  // Données pour le graphique (mockées pour l'instant - à remplacer par historique réel)
  const portfolioData = [
    { time: '00:00', value: globalStatus ? globalStatus.total_capital * 0.95 : 5000 },
    { time: '04:00', value: globalStatus ? globalStatus.total_capital * 0.98 : 5150 },
    { time: '08:00', value: globalStatus ? globalStatus.total_capital * 1.02 : 5280 },
    { time: '12:00', value: globalStatus ? globalStatus.total_capital * 0.99 : 5190 },
    { time: '16:00', value: globalStatus ? globalStatus.total_capital : 1000 },
    { time: '20:00', value: globalStatus ? globalStatus.total_capital * 0.97 : 5380 },
  ];

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
            Vérifiez que le bot est démarré: <code className="bg-gray-800 px-2 py-1 rounded">python src/autobot/v2/main.py</code>
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
