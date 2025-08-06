import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { TrendingUp, Target, Shield, Zap, Eye, Activity } from 'lucide-react';

const generateEquityCurveFromRuns = (runs: any[]) => {
  if (runs.length === 0) return [];
  
  let value = 500;
  return runs.slice(0, 6).map((run, index) => {
    value = value * (1 + run.return / 100);
    return {
      time: `Run ${index + 1}`,
      value: Math.round(value)
    };
  });
};

const Backtest: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [selectedStrategy, setSelectedStrategy] = useState<any>(null);
  const [backtestData, setBacktestData] = useState<{
    strategies: any[];
    equityCurve: any[];
    monthlyResults: any[];
    runs: any[];
  }>({
    strategies: [],
    equityCurve: [],
    monthlyResults: [],
    runs: []
  });

  useEffect(() => {
    const fetchBacktestData = async () => {
      try {
        const [strategiesResponse, runsResponse] = await Promise.all([
          axios.get('/api/backtest/strategies'),
          axios.get('/api/backtest/runs')
        ]);
        
        const strategies = strategiesResponse.data.map((strategy: any) => ({
          name: strategy.name,
          description: strategy.description,
          performance: `${strategy.performance > 0 ? '+' : ''}${strategy.performance.toFixed(1)}%`,
          winRate: `${strategy.winRate.toFixed(0)}%`,
          sharpe: strategy.sharpe.toFixed(1),
          status: strategy.status
        }));
        
        const backtestRuns = runsResponse.data.runs || [];

        const equityCurve = backtestRuns.length > 0 ? 
          generateEquityCurveFromRuns(backtestRuns) :
          [
            { time: 'Début', value: 500 },
            { time: 'Jour 5', value: 500 * (1 + (strategies[0]?.performance || 0) / 100 * 0.2) },
            { time: 'Jour 10', value: 500 * (1 + (strategies[0]?.performance || 0) / 100 * 0.4) },
            { time: 'Jour 15', value: 500 * (1 + (strategies[0]?.performance || 0) / 100 * 0.6) },
            { time: 'Jour 20', value: 500 * (1 + (strategies[0]?.performance || 0) / 100 * 0.8) },
            { time: 'Jour 25', value: 500 * (1 + (strategies[0]?.performance || 0) / 100) },
          ];

        const monthlyResults = [
          { month: 'Jan', return: 8.2 },
          { month: 'Fév', return: 12.1 },
          { month: 'Mar', return: -2.3 },
          { month: 'Avr', return: 15.7 },
          { month: 'Mai', return: 9.4 },
          { month: 'Juin', return: 18.9 },
        ];

        setBacktestData({
          strategies,
          equityCurve,
          monthlyResults,
          runs: backtestRuns
        });
      } catch (error) {
        console.error('Error fetching backtest data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchBacktestData();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="text-emerald-400 text-xl">Chargement des données de backtest...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white p-4 lg:p-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6 lg:mb-8">
          <h1 className="text-3xl lg:text-4xl font-bold text-emerald-400 mb-2">
            Backtest des Stratégies
          </h1>
          <p className="text-gray-400 text-base lg:text-lg">
            Analyse des performances historiques et optimisation des stratégies de trading
          </p>
        </div>

        {/* Recent Backtest Activity */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 mb-6 lg:mb-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
            <Activity className="w-5 lg:w-6 h-5 lg:h-6" />
            <span>Activité de Backtest Récente</span>
          </h3>
          <div className="space-y-3">
            {backtestData.runs && backtestData.runs.length > 0 ? (
              backtestData.runs.slice(0, 10).map((run: any, index: number) => (
                <div key={index} className="flex justify-between items-center p-3 bg-gray-700/30 rounded-lg border border-gray-600/20">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3">
                      <span className="text-white font-medium">{run.strategy}</span>
                      <span className="text-gray-400 text-sm">{run.symbol}</span>
                      <span className="text-gray-500 text-xs">{run.timeframe}</span>
                    </div>
                    <div className="text-gray-400 text-xs mt-1">{run.date}</div>
                  </div>
                  <div className="flex items-center space-x-4">
                    <div className="text-right">
                      <div className={`font-bold ${run.return > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {run.return > 0 ? '+' : ''}{run.return}%
                      </div>
                      <div className="text-gray-400 text-xs">Sharpe: {run.sharpe}</div>
                    </div>
                    {run.auto_generated && (
                      <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded">Auto</span>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center text-gray-400 py-8">
                Aucune activité de backtest récente. Les backtests automatiques apparaîtront ici.
              </div>
            )}
          </div>
        </div>

        {/* Performance Overview */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 lg:gap-8 mb-6 lg:mb-8">
          {/* Equity Curve */}
          <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
            <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
              <TrendingUp className="w-5 lg:w-6 h-5 lg:h-6" />
              <span>Courbe d'Équité</span>
            </h3>
            <div className="h-64 lg:h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={backtestData.equityCurve}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="time" stroke="#9CA3AF" fontSize={12} />
                  <YAxis stroke="#9CA3AF" fontSize={12} />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#1F2937', 
                      border: '1px solid #374151',
                      borderRadius: '8px',
                      color: '#F3F4F6'
                    }} 
                  />
                  <Line 
                    type="monotone" 
                    dataKey="value" 
                    stroke="#10B981" 
                    strokeWidth={3}
                    dot={{ fill: '#10B981', strokeWidth: 2, r: 4 }}
                    activeDot={{ r: 6, stroke: '#10B981', strokeWidth: 2 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Monthly Returns */}
          <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
            <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
              <Target className="w-5 lg:w-6 h-5 lg:h-6" />
              <span>Rendements Mensuels</span>
            </h3>
            <div className="h-64 lg:h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={backtestData.monthlyResults}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="month" stroke="#9CA3AF" fontSize={12} />
                  <YAxis stroke="#9CA3AF" fontSize={12} />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#1F2937', 
                      border: '1px solid #374151',
                      borderRadius: '8px',
                      color: '#F3F4F6'
                    }} 
                  />
                  <Bar 
                    dataKey="return" 
                    fill="#10B981"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
        {/* Recent Backtest Activity */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 mb-6 lg:mb-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
            <Activity className="w-5 lg:w-6 h-5 lg:h-6" />
            <span>Activité de Backtest Récente</span>
          </h3>
          <div className="space-y-3">
            {backtestData.runs && backtestData.runs.length > 0 ? (
              backtestData.runs.slice(0, 10).map((run: any, index: number) => (
                <div key={index} className="flex justify-between items-center p-3 bg-gray-700/30 rounded-lg border border-gray-600/20">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3">
                      <span className="text-white font-medium">{run.strategy}</span>
                      <span className="text-gray-400 text-sm">{run.symbol}</span>
                      <span className="text-gray-500 text-xs">{run.timeframe}</span>
                    </div>
                    <div className="text-gray-400 text-xs mt-1">{run.date}</div>
                  </div>
                  <div className="flex items-center space-x-4">
                    <div className="text-right">
                      <div className={`font-bold ${run.return > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {run.return > 0 ? '+' : ''}{run.return}%
                      </div>
                      <div className="text-gray-400 text-xs">Sharpe: {run.sharpe}</div>
                    </div>
                    {run.auto_generated && (
                      <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded">Auto</span>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center text-gray-400 py-8">
                Aucune activité de backtest récente. Les backtests automatiques apparaîtront ici.
              </div>
            )}
          </div>
        </div>


            </div>
          </div>
        </div>

        {/* Strategies Grid */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
            <Shield className="w-5 lg:w-6 h-5 lg:h-6" />
            <span>Stratégies Identifiées par l'IA</span>
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 lg:gap-6">
            {backtestData.strategies.map((strategy, index) => (
              <div 
                key={index}
                className="bg-gray-700/30 border border-gray-600/20 rounded-xl p-4 lg:p-6 hover:bg-gray-700/50 transition-all duration-300 cursor-pointer group"
                onClick={() => setSelectedStrategy(strategy)}
              >
                <div className="flex items-start justify-between mb-3">
                  <h4 className="text-lg font-semibold text-white group-hover:text-emerald-400 transition-colors">
                    {strategy.name}
                  </h4>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                    strategy.status === 'Active' 
                      ? 'bg-emerald-500/20 text-emerald-400' 
                      : 'bg-gray-500/20 text-gray-400'
                  }`}>
                    {strategy.status}
                  </span>
                </div>
                
                <p className="text-gray-400 text-sm mb-4 line-clamp-2">
                  {strategy.description}
                </p>
                
                <div className="grid grid-cols-3 gap-3">
                  <div className="text-center">
                    <div className={`text-lg font-bold ${
                      strategy.performance.includes('+') ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                      {strategy.performance}
                    </div>
                    <div className="text-xs text-gray-500">Performance</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-blue-400">{strategy.winRate}</div>
                    <div className="text-xs text-gray-500">Win Rate</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-purple-400">{strategy.sharpe}</div>
                    <div className="text-xs text-gray-500">Sharpe</div>
                  </div>
                </div>
                
                <div className="mt-4 flex items-center justify-between">
                  <button className="flex items-center space-x-1 text-emerald-400 hover:text-emerald-300 transition-colors">
                    <Eye className="w-4 h-4" />
                    <span className="text-sm">Voir détails</span>
                  </button>
                  <Zap className="w-4 h-4 text-yellow-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Backtest;
