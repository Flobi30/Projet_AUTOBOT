import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import MetricCard from '../components/ui/MetricCard';
import LiveLog from '../components/ui/LiveLog';
import { TrendingUp, DollarSign, Target, AlertTriangle, Activity } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import Skeleton from 'react-loading-skeleton';
import 'react-loading-skeleton/dist/skeleton.css';

const SkeletonGrid = () => (
  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
    <Skeleton height={120} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
    <Skeleton height={120} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
    <Skeleton height={120} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
  </div>
);

const LiveTrading: React.FC = () => {
  const { capitalTotal, setCapitalTotal } = useAppStore();
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Simule un chargement de données
    const timer = setTimeout(() => {
      setCapitalTotal(5420); // Met à jour le store global
      setIsLoading(false);
    }, 1500);
    return () => clearTimeout(timer);
  }, [setCapitalTotal]);

  const portfolioData = [
    { time: '00:00', value: 5000 },
    { time: '04:00', value: 5150 },
    { time: '08:00', value: 5280 },
    { time: '12:00', value: 5190 },
    { time: '16:00', value: 5420 },
    { time: '20:00', value: 5380 },
  ];

  const openPositions = [
    { pair: 'BTC/USD', side: 'LONG', size: '0.15 BTC', entry: '45,230€', current: '46,150€', pnl: '+920€', pnlPercent: '+2.03%' },
    { pair: 'ETH/USD', side: 'SHORT', size: '3.2 ETH', entry: '2,450€', current: '2,420€', pnl: '+96€', pnlPercent: '+1.22%' },
    { pair: 'EUR/USD', side: 'LONG', size: '2,500 EUR', entry: '1.0845', current: '1.0835', pnl: '-25€', pnlPercent: '-0.92%' },
  ];

  const marketAlerts = [
    { type: 'opportunity', message: 'Signal d\'achat fort détecté sur BTC/USD', time: '14:32', severity: 'high' },
    { type: 'warning', message: 'Volatilité élevée sur EUR/USD - Attention', time: '14:28', severity: 'medium' },
    { type: 'info', message: 'Résistance cassée sur ETH/USD - Suivi en cours', time: '14:25', severity: 'low' },
  ];

  if (isLoading) {
    return (
      <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
        <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
          <Skeleton width={300} height={40} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
          <Skeleton width={400} height={20} baseColor="#1a1a1a" highlightColor="#2a2a2a" className="mt-2" />
        </div>
        <SkeletonGrid />
        <Skeleton height={400} baseColor="#1a1a1a" highlightColor="#2a2a2a" />
      </div>
    );
  }

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      {/* Header */}
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex items-center space-x-3 mb-3">
          <TrendingUp className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400" />
          <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
            Live Trading
          </h1>
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">Performances en temps réel du robot de trading.</p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <MetricCard title="Rendement Total" value="+8.42%" change="+0.15%" icon={<TrendingUp className="w-5 h-5" />} />
        <MetricCard title="Profit/Perte (24h)" value="+118€" change="+2.18%" icon={<DollarSign className="w-5 h-5" />} />
        <MetricCard title="Ratio de Sharpe" value="1.84" icon={<Target className="w-5 h-5" />} />
      </div>
      
      {/* Portfolio Evolution Chart */}
      <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 mb-6 lg:mb-8 shadow-2xl">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6">
          <h2 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-2 sm:mb-0">
            Évolution du Portefeuille
          </h2>
          <div className="text-left sm:text-right">
            <div className="text-2xl lg:text-3xl font-bold text-white">{capitalTotal.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })}</div>
            <div className="text-emerald-400 text-sm">+420€ (+8.42%)</div>
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
            <span className="text-sm bg-emerald-500/20 text-emerald-400 px-2 py-1 rounded-lg font-normal">{openPositions.length} actives</span>
          </h3>
          <div className="space-y-3">
            {openPositions.map((position, index) => (
              <div key={index} className="p-4 bg-gray-700/50 rounded-xl border border-gray-600/30">
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center space-x-3"><span className="text-white font-bold">{position.pair}</span><span className={`px-2 py-1 rounded text-xs font-bold ${position.side === 'LONG' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-blue-500/20 text-blue-400'}`}>{position.side}</span></div>
                  <div className="text-right"><div className={`font-bold ${position.pnl.startsWith('+') ? 'text-emerald-400' : 'text-red-400'}`}>{position.pnl}</div><div className={`text-sm ${position.pnlPercent.startsWith('+') ? 'text-emerald-400' : 'text-red-400'}`}>{position.pnlPercent}</div></div>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div><span className="text-gray-400">Taille: </span><span className="text-white">{position.size}</span></div>
                  <div><span className="text-gray-400">Entrée: </span><span className="text-white">{position.entry}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
        
        {/* NOUVEAU: Journal d'Activité en Temps Réel */}
        <LiveLog />
      </div>
    </div>
  );
};

export default LiveTrading;
