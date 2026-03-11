import React from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import MetricCard from '../components/ui/MetricCard';
import { PieChart, Target, TrendingUp, Shield, Zap, BarChart3 } from 'lucide-react';

const Analytics: React.FC = () => {
  const performanceData = [
    { date: '01/01', portfolio: 5000, benchmark: 5000 },
    { date: '05/01', portfolio: 5120, benchmark: 5050 },
    { date: '10/01', portfolio: 5280, benchmark: 5100 },
    { date: '15/01', portfolio: 5190, benchmark: 5080 },
    { date: '20/01', portfolio: 5420, benchmark: 5150 },
  ];

  const marketAnalysis = [
    { pair: 'BTC/USD', trend: 'Haussier', signal: 'BUY' },
    { pair: 'ETH/USD', trend: 'Neutre', signal: 'HOLD' },
    { pair: 'EUR/USD', trend: 'Baissier', signal: 'SELL' },
  ];

  return (
    <div className="p-8 bg-gray-900 min-h-screen">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center space-x-3 mb-3">
          <PieChart className="w-8 h-8 text-emerald-400" />
          <h1 className="text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
            Analytics
          </h1>
        </div>
        <p className="text-gray-400 text-lg">Analyses avancées et métriques de performance.</p>
      </div>

      {/* Key Performance Indicators */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <MetricCard title="Rendement Annualisé" value="24.8%" icon={<TrendingUp className="w-5 h-5" />} />
        <MetricCard title="Ratio de Sharpe" value="1.84" icon={<Target className="w-5 h-5" />} />
        <MetricCard title="Taux de Réussite" value="68%" icon={<BarChart3 className="w-5 h-5" />} />
      </div>

      {/* Performance vs Benchmark */}
      <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-8 mb-8 shadow-2xl">
        <h3 className="text-2xl font-bold text-emerald-400 mb-6">Performance vs Benchmark</h3>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={performanceData}>
              <defs>
                <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/><stop offset="95%" stopColor="#10B981" stopOpacity={0}/></linearGradient>
                <linearGradient id="benchmarkGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#6B7280" stopOpacity={0.3}/><stop offset="95%" stopColor="#6B7280" stopOpacity={0}/></linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" stroke="#9CA3AF" />
              <YAxis stroke="#9CA3AF" />
              <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #10B981', borderRadius: '12px' }} />
              <Area type="monotone" dataKey="benchmark" stroke="#6B7280" strokeWidth={2} fill="url(#benchmarkGradient)" name="Benchmark" />
              <Area type="monotone" dataKey="portfolio" stroke="#10B981" strokeWidth={3} fill="url(#portfolioGradient)" name="AUTOBOT" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        {/* Risk Metrics */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-8 shadow-2xl">
          <h3 className="text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
            <Shield className="w-6 h-6" />
            <span>Métriques de Risque</span>
          </h3>
          <div className="space-y-4">
            {[
              { label: 'Volatilité', value: '12.5%', color: 'text-blue-400' },
              { label: 'Alpha', value: '2.3%', color: 'text-emerald-400' },
              { label: 'Max Drawdown', value: '-4.2%', color: 'text-red-400' },
            ].map((metric) => (
              <div key={metric.label} className="flex justify-between items-center py-2 border-b border-gray-700/50 last:border-b-0">
                <span className="text-gray-400 font-medium">{metric.label}</span>
                <span className={`font-bold text-lg ${metric.color}`}>{metric.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Market Analysis */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-8 shadow-2xl">
          <h3 className="text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
            <Zap className="w-6 h-6" />
            <span>Analyse de Marché IA</span>
          </h3>
          <div className="space-y-3">
            {marketAnalysis.map((analysis, index) => (
              <div key={index} className="flex justify-between items-center p-4 bg-gray-700/50 rounded-xl">
                <div>
                  <span className="text-white font-bold">{analysis.pair}</span>
                  <span className="text-gray-300 ml-3">{analysis.trend}</span>
                </div>
                <span className={`px-3 py-1 rounded-lg text-sm font-bold ${
                  analysis.signal === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' :
                  analysis.signal === 'SELL' ? 'bg-red-500/20 text-red-400' :
                  'bg-yellow-500/20 text-yellow-400'
                }`}>
                  {analysis.signal}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Analytics;
