import React, { useState, useEffect } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import MetricCard from '../components/ui/MetricCard';
import { PieChart, Target, TrendingUp, Shield, BarChart3, Loader } from 'lucide-react';

const API_BASE_URL = 'http://178.104.0.255:8080';

const Analytics: React.FC = () => {
  const [performanceData, setPerformanceData] = useState<any[]>([]);
  const [metrics, setMetrics] = useState({
    rendement: '—',
    sharpe: '—',
    winRate: '—',
    volatility: '—',
    maxDrawdown: '—'
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const capitalRes = await fetch(`${API_BASE_URL}/api/capital`);
        if (capitalRes.ok) {
          const capitalData = await capitalRes.json();
          const pnlPercent = capitalData.total_capital > 0 
            ? (capitalData.total_profit / capitalData.total_invested * 100).toFixed(1)
            : '0.0';
          
          setMetrics(prev => ({
            ...prev,
            rendement: `${pnlPercent}%`,
          }));
        }

        const historyRes = await fetch(`${API_BASE_URL}/api/history?days=7`);
        if (historyRes.ok) {
          const historyData = await historyRes.json();
          if (historyData.history && historyData.history.length > 0) {
            setPerformanceData(historyData.history.map((item: any) => ({
              date: new Date(item.timestamp).toLocaleDateString('fr-FR'),
              portfolio: item.value,
            })));
          }
        }

        setIsLoading(false);
      } catch (err) {
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
        <Loader className="w-8 h-8 text-emerald-400 animate-spin" />
        <span className="ml-3 text-emerald-400">Chargement...</span>
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