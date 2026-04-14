import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import MetricCard from '../components/ui/MetricCard';
import Modal from '../components/ui/Modal';
import StrategyDetailModal from '../components/ui/StrategyDetailModal';
import { BarChart3, Brain, Cpu, Target, TrendingUp, Calendar, Loader } from 'lucide-react';

const API_BASE_URL = '';
const API_TOKEN = import.meta.env.VITE_DASHBOARD_API_TOKEN || window.localStorage.getItem('DASHBOARD_API_TOKEN') || '';// no hardcoded secret

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
  const [isLoading, setIsLoading] = useState(true);
  const [metrics, setMetrics] = useState({
    performance: '—',
    sharpe: '—',
    strategies: '—'
  });
  const [backtestData, setBacktestData] = useState<any[]>([]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch pour remplir les métriques si disponibles
        const capitalRes = await fetch(`${API_BASE_URL}/api/capital`, { headers: { "Authorization": `Bearer ${API_TOKEN}` } });
        if (capitalRes.ok) {
          const data = await capitalRes.json();
          const perf = data.total_invested > 0 
            ? ((data.total_profit / data.total_invested) * 100).toFixed(2)
            : '0.00';
          setMetrics({
            performance: `+${perf}%`,
            sharpe: '—',
            strategies: '1'
          });
        }

        // Données historiques pour le graphique
        const historyRes = await fetch(`${API_BASE_URL}/api/history?days=30`, { headers: { "Authorization": `Bearer ${API_TOKEN}` } });
        if (historyRes.ok) {
          const historyData = await historyRes.json();
          if (historyData.history) {
            const formatted = historyData.history.map((item: any, idx: number) => ({
              time: `Jour ${idx * 5}`,
              value: item.value
            }));
            setBacktestData(formatted);
          }
        }

        setIsLoading(false);
      } catch (err) {
        setIsLoading(false);
      }
    };

    fetchData();
  }, []);

  const learnedStrategies: Strategy[] = [
    { 
      name: 'Grid Trading XBT/EUR', 
      description: 'Grille de trading sur Bitcoin/Euro', 
      performance: metrics.performance, 
      winRate: '—', 
      sharpe: '—', 
      status: 'Active' 
    },
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

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex items-center space-x-3 mb-3">
          <BarChart3 className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400" />
          <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">Backtest</h1>
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">Analyse des strategies et performances.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <MetricCard title="Performance" value={metrics.performance} icon={<TrendingUp className="w-5 h-5" />} />
        <MetricCard title="Ratio de Sharpe" value={metrics.sharpe} icon={<Target className="w-5 h-5" />} />
        <MetricCard title="Strategies" value={metrics.strategies} icon={<Cpu className="w-5 h-5" />} />
      </div>

      <div className="bg-gray-800 rounded-2xl p-4 lg:p-8 mb-6 lg:mb-8">
        <h2 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">Performance en temps reel</h2>
        {backtestData.length > 0 ? (
          <div className="h-64 lg:h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={backtestData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="time" stroke="#9CA3AF" />
                <YAxis stroke="#9CA3AF" />
                <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #10B981' }} />
                <Line type="monotone" dataKey="value" stroke="#10B981" strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-gray-500 text-center py-8">
            Pas encore d historique de performance disponible.
          </div>
        )}
      </div>

      <div className="bg-gray-800 rounded-2xl p-4 lg:p-8">
        <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">Strategies Actives</h3>
        <div className="space-y-3">
          {learnedStrategies.map((strategy, idx) => (
            <div key={idx} className="p-4 bg-gray-700/50 rounded-xl cursor-pointer" onClick={() => setSelectedStrategy(strategy)}>
              <div className="flex justify-between items-start">
                <div>
                  <h4 className="text-white font-bold">{strategy.name}</h4>
                  <p className="text-gray-400 text-sm">{strategy.description}</p>
                </div>
                <span className="text-emerald-400 font-bold">{strategy.performance}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Backtest;