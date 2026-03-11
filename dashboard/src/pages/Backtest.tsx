import React, { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import MetricCard from '../components/ui/MetricCard';
import Modal from '../components/ui/Modal';
import StrategyDetailModal from '../components/ui/StrategyDetailModal';
import { BarChart3, Brain, Cpu, Target, TrendingUp, Calendar } from 'lucide-react';

// Définition d'un type plus précis pour une stratégie
export interface Strategy {
  name: string;
  description: string;
  performance: string;
  winRate: string;
  sharpe: string;
  status: 'Active' | 'En observation';
}

const Backtest: React.FC = () => {
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);

  const backtestData = [
    { time: 'Début', value: 500 }, { time: 'Jour 5', value: 512 }, { time: 'Jour 10', value: 508 },
    { time: 'Jour 15', value: 525 }, { time: 'Jour 20', value: 531 }, { time: 'Jour 25', value: 542 },
    { time: 'Fin', value: 538 },
  ];

  const learnedStrategies: Strategy[] = [
    { name: 'Scalping Volatilité BTC', description: 'Trading haute fréquence sur micro-mouvements', performance: '+18.2%', winRate: '75%', sharpe: '2.3', status: 'Active' },
    { name: 'Swing Trading ETH/USD', description: 'Positions moyen terme sur tendances', performance: '+12.5%', winRate: '68%', sharpe: '1.9', status: 'Active' },
    { name: 'Arbitrage Forex EUR/GBP', description: 'Exploitation des écarts de prix', performance: '+7.8%', winRate: '85%', sharpe: '2.8', status: 'En observation' },
  ];

  const monthlyResults = [
    { month: 'Oct', profit: 45 }, { month: 'Nov', profit: 62 }, { month: 'Déc', profit: 38 }, { month: 'Jan', profit: 74 },
  ];

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      {/* Header */}
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex items-center space-x-3 mb-3">
          <BarChart3 className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400" />
          <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">Backtest</h1>
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">Analyse des stratégies et performances historiques.</p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <MetricCard title="Performance Simulée" value="+7.60%" icon={<TrendingUp className="w-5 h-5" />} />
        <MetricCard title="Ratio de Sharpe" value="1.45" icon={<Target className="w-5 h-5" />} />
        <MetricCard title="Stratégies Testées" value="24" change="+5" icon={<Cpu className="w-5 h-5" />} />
      </div>

      {/* Backtest Chart */}
      <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 mb-6 lg:mb-8 shadow-2xl">
        <h2 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">Simulation de Stratégie (30 jours)</h2>
        <div className="h-64 lg:h-80">
          <ResponsiveContainer width="100%" height="100%"><LineChart data={backtestData}><defs><linearGradient id="backtestGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/><stop offset="95%" stopColor="#10B981" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="#374151" /><XAxis dataKey="time" stroke="#9CA3AF" fontSize={12} /><YAxis stroke="#9CA3AF" fontSize={12} /><Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #10B981', borderRadius: '12px' }} /><Line type="monotone" dataKey="value" stroke="#10B981" strokeWidth={3} dot={false} fill="url(#backtestGradient)" /></LineChart></ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8">
        {/* Stratégies Apprises par l'IA */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2"><Brain className="w-5 lg:w-6 h-5 lg:h-6" /><span>Stratégies Apprises par l'IA</span></h3>
          <div className="space-y-4">
            {learnedStrategies.map((strategy, index) => (
              <div 
                key={index} 
                className="p-4 bg-gray-700/50 rounded-xl border border-gray-600/30 cursor-pointer hover:bg-gray-700/80 hover:border-emerald-500/50 transition-all"
                onClick={() => setSelectedStrategy(strategy)}
              >
                <div className="flex justify-between items-start mb-2">
                  <div><span className="text-white font-bold">{strategy.name}</span><p className="text-gray-400 text-sm">{strategy.description}</p></div>
                  <span className={`px-2 py-1 rounded text-xs font-bold ${strategy.status === 'Active' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-blue-500/20 text-blue-400'}`}>{strategy.status}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-sm mt-3">
                  <div><span className="text-gray-400 text-xs block">Performance</span><span className="text-white font-bold">{strategy.performance}</span></div>
                  <div><span className="text-gray-400 text-xs block">Win Rate</span><span className="text-white font-bold">{strategy.winRate}</span></div>
                  <div><span className="text-gray-400 text-xs block">Sharpe</span><span className="text-white font-bold">{strategy.sharpe}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Résultats Mensuels */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2"><Calendar className="w-5 lg:w-6 h-5 lg:h-6" /><span>Profits Mensuels</span></h3>
          <div className="h-48 mb-6">
            <ResponsiveContainer width="100%" height="100%"><BarChart data={monthlyResults}><CartesianGrid strokeDasharray="3 3" stroke="#374151" /><XAxis dataKey="month" stroke="#9CA3AF" fontSize={12} /><YAxis stroke="#9CA3AF" fontSize={12} /><Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #10B981', borderRadius: '12px' }} /><Bar dataKey="profit" fill="#10B981" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
          </div>
          <div className="space-y-3"><h4 className="text-lg font-bold text-white mb-3">Statistiques Clés</h4>
            {[{ label: 'Profit/Perte Net', value: '+219€', color: 'text-emerald-400' }, { label: 'Taux de Réussite', value: '67%', color: 'text-blue-400' }, { label: 'Drawdown Max', value: '-3.1%', color: 'text-red-400' }].map((stat) => (
              <div key={stat.label} className="flex justify-between items-center py-2 border-b border-gray-700/50 last:border-b-0"><span className="text-gray-400 font-medium">{stat.label}</span><span className={`font-bold ${stat.color}`}>{stat.value}</span></div>
            ))}
          </div>
        </div>
      </div>

      {/* Modal pour les détails de la stratégie */}
      <Modal 
        isOpen={!!selectedStrategy} 
        onClose={() => setSelectedStrategy(null)}
        title={selectedStrategy?.name || 'Détails de la Stratégie'}
      >
        {selectedStrategy && <StrategyDetailModal strategy={selectedStrategy} />}
      </Modal>
    </div>
  );
};

export default Backtest;
