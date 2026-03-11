import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Strategy } from '../../pages/Backtest';

interface StrategyDetailModalProps {
  strategy: Strategy;
}

const StrategyDetailModal: React.FC<StrategyDetailModalProps> = ({ strategy }) => {
  // Données factices pour le graphique de performance de la stratégie
  const strategyPerformanceData = [
    { day: 1, value: 1000 }, { day: 5, value: 1025 }, { day: 10, value: 1015 },
    { day: 15, value: 1050 }, { day: 20, value: 1080 }, { day: 25, value: 1120 },
    { day: 30, value: 1150 },
  ];

  const detailedStats = [
    { label: 'Profit/Perte Total', value: '+150€', color: 'text-emerald-400' },
    { label: 'Profit Moyen / Trade', value: '+12.5€', color: 'text-emerald-400' },
    { label: 'Perte Moyenne / Trade', value: '-8.2€', color: 'text-red-400' },
    { label: 'Max Drawdown', value: '-3.5%', color: 'text-red-400' },
    { label: 'Durée Moyenne / Trade', value: '4h 15min', color: 'text-blue-400' },
  ];

  return (
    <div className="space-y-6">
      <p className="text-gray-400">{strategy.description}</p>
      
      {/* Performance Chart */}
      <div>
        <h4 className="text-lg font-bold text-white mb-3">Performance Historique (30 jours)</h4>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={strategyPerformanceData}>
              <defs>
                <linearGradient id="strategyDetailGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="day" stroke="#9CA3AF" fontSize={12} unit="j" />
              <YAxis stroke="#9CA3AF" fontSize={12} />
              <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #10B981', borderRadius: '12px' }} />
              <Line type="monotone" dataKey="value" stroke="#10B981" strokeWidth={2} dot={false} fill="url(#strategyDetailGradient)" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Detailed Stats */}
      <div>
        <h4 className="text-lg font-bold text-white mb-3">Statistiques Détaillées</h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Base stats from the card */}
          <div className="p-3 bg-gray-700/50 rounded-lg"><span className="text-gray-400">Performance</span><div className="text-white font-bold text-xl">{strategy.performance}</div></div>
          <div className="p-3 bg-gray-700/50 rounded-lg"><span className="text-gray-400">Taux de Réussite</span><div className="text-white font-bold text-xl">{strategy.winRate}</div></div>
          <div className="p-3 bg-gray-700/50 rounded-lg"><span className="text-gray-400">Ratio de Sharpe</span><div className="text-white font-bold text-xl">{strategy.sharpe}</div></div>
          
          {/* Detailed stats */}
          {detailedStats.map(stat => (
            <div key={stat.label} className="p-3 bg-gray-700/50 rounded-lg">
              <span className="text-gray-400">{stat.label}</span>
              <div className={`font-bold text-xl ${stat.color}`}>{stat.value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default StrategyDetailModal;
