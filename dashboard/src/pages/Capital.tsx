import React, { useState, useEffect, useCallback } from 'react';
import { Wallet, DollarSign, CreditCard, TrendingUp, TrendingDown, Loader, ExternalLink } from 'lucide-react';
import MetricCard from '../components/ui/MetricCard';
import { useAppStore } from '../store/useAppStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

interface CapitalData {
  total_capital: number;
  total_profit: number;
  total_invested: number;
  available_cash: number;
  currency: string;
  timestamp: string;
}

interface TradeData {
  id: string;
  instance_id: string;
  instance_name: string;
  pair: string;
  side: string;
  amount: number;
  price: number;
  pnl: number;
  timestamp: string;
  strategy: string;
}

const Capital: React.FC = () => {
  const { setCapitalTotal } = useAppStore();
  // État pour les données réelles de l'API
  const [capitalData, setCapitalData] = useState<CapitalData | null>(null);
  const [trades, setTrades] = useState<TradeData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch des données capital et trades depuis l'API
  const fetchCapitalData = useCallback(async () => {
    try {
      setError(null);

      // Fetch capital details
      const capitalRes = await fetch(`${API_BASE_URL}/api/capital`);
      if (capitalRes.ok) {
        const data: CapitalData = await capitalRes.json();
        setCapitalData(data);
        setCapitalTotal(data.total_capital);
      } else {
        // Fallback sur /api/status si /api/capital n'existe pas encore
        const statusRes = await fetch(`${API_BASE_URL}/api/status`);
        if (!statusRes.ok) throw new Error(`API Error: ${statusRes.status}`);
        const statusData = await statusRes.json();
        const fallback: CapitalData = {
          total_capital: statusData.total_capital || 0,
          total_profit: statusData.total_profit || 0,
          total_invested: (statusData.total_capital || 0) - (statusData.total_profit || 0),
          available_cash: 0,  // N/A en mode fallback
          currency: 'EUR',
          timestamp: new Date().toISOString(),
        };
        setCapitalData(fallback);
        setCapitalTotal(fallback.total_capital);
      }

      // Fetch recent trades
      const tradesRes = await fetch(`${API_BASE_URL}/api/trades?limit=10`);
      if (tradesRes.ok) {
        const tradesData = await tradesRes.json();
        setTrades(tradesData.trades || []);
      }

      setIsLoading(false);
    } catch (err) {
      console.error('Erreur connexion API Capital:', err);
      setError(err instanceof Error ? err.message : 'Erreur de connexion');
      setIsLoading(false);
    }
  }, [setCapitalTotal]);

  useEffect(() => {
    fetchCapitalData();
    const interval = setInterval(fetchCapitalData, 5000);
    return () => clearInterval(interval);
  }, [fetchCapitalData]);

  const handleDepositClick = () => {
    // Redirection vers Kraken Pro pour dépôt EUR
    window.open('https://pro.kraken.com/funding?asset=ZEUR', '_blank');
  };

  const handleWithdrawClick = () => {
    // Redirection vers Kraken Pro pour retrait EUR
    window.open('https://pro.kraken.com/funding?asset=ZEUR&action=withdraw', '_blank');
  };

  // Formatage monétaire
  const formatCurrency = (value: number): string => {
    return value.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
  };

  // Transformer les trades en transactions affichables
  const recentTransactions = trades.length > 0
    ? trades.map((trade) => ({
        type: trade.pnl >= 0 ? 'profit' : 'withdraw',
        amount: `${trade.pnl >= 0 ? '+' : ''}${formatCurrency(trade.pnl)}`,
        description: `${trade.side} ${trade.pair} (${trade.instance_name})`,
        date: new Date(trade.timestamp).toLocaleDateString('fr-FR'),
      }))
    : [];

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      {/* Header */}
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex items-center space-x-3 mb-3">
          <Wallet className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400" />
          <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
            Portail Capital
          </h1>
          {isLoading && <Loader className="w-5 h-5 text-emerald-400 animate-spin" />}
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">Gérez vos fonds de manière sécurisée.</p>
        {error && (
          <div className="mt-2 bg-red-500/20 border border-red-500/50 rounded-lg p-3 text-red-400 text-sm">
            ⚠️ {error} — Les données affichées peuvent ne pas être à jour.
          </div>
        )}
      </div>

      {/* Metrics - données réelles de l'API */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <MetricCard
          title="Capital Total"
          value={capitalData ? formatCurrency(capitalData.total_capital) : '—'}
          icon={<DollarSign className="w-5 h-5" />}
        />
        <MetricCard
          title="Profit Réalisé"
          value={capitalData ? formatCurrency(capitalData.total_profit) : '—'}
          icon={<TrendingUp className="w-5 h-5" />}
          isPositive={(capitalData?.total_profit ?? 0) >= 0}
          change={capitalData && capitalData.total_capital > 0
            ? `${((capitalData.total_profit / capitalData.total_capital) * 100).toFixed(2)}%`
            : undefined}
        />
        <MetricCard
          title="Capital Investi"
          value={capitalData ? formatCurrency(capitalData.total_invested) : '—'}
          icon={<CreditCard className="w-5 h-5" />}
        />
        <MetricCard
          title="Cash Disponible"
          value={capitalData ? (capitalData.available_cash === 0 ? '—' : formatCurrency(capitalData.available_cash)) : '—'}
          icon={<Wallet className="w-5 h-5" />}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8">
        {/* Actions Module */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl flex flex-col justify-center">
            <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 text-center">Actions Rapides</h3>
            <div className="flex flex-col sm:flex-row gap-4">
                <button 
                    onClick={handleDepositClick}
                    className="flex-1 flex items-center justify-center space-x-2 rounded-xl bg-emerald-500 px-4 py-3 text-base font-semibold text-white shadow-lg shadow-emerald-500/20 transition-all hover:bg-emerald-600"
                >
                    <ExternalLink className="w-5 h-5" />
                    <span>Déposer sur Kraken</span>
                </button>
                <button 
                    onClick={handleWithdrawClick}
                    className="flex-1 flex items-center justify-center space-x-2 rounded-xl bg-blue-500 px-4 py-3 text-base font-semibold text-white shadow-lg shadow-blue-500/20 transition-all hover:bg-blue-600"
                >
                    <ExternalLink className="w-5 h-5" />
                    <span>Retrait sur Kraken</span>
                </button>
            </div>
        </div>

        {/* Recent Transactions - données réelles */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">Historique des Transactions</h3>
          <div className="space-y-3">
            {recentTransactions.length === 0 ? (
              <div className="text-gray-500 text-center py-8">
                Aucune transaction récente
              </div>
            ) : (
              recentTransactions.map((transaction, index) => (
                <div key={index} className="flex flex-col sm:flex-row sm:justify-between sm:items-center p-3 lg:p-4 bg-gray-700/50 rounded-xl space-y-2 sm:space-y-0">
                  <div className="flex items-center space-x-3">
                    <div className={`w-8 lg:w-10 h-8 lg:h-10 rounded-lg flex items-center justify-center ${
                      transaction.type === 'deposit' || transaction.type === 'profit' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      {transaction.type === 'withdraw' ? 
                        <TrendingDown className="w-4 lg:w-5 h-4 lg:h-5" /> : 
                        <TrendingUp className="w-4 lg:w-5 h-4 lg:h-5" />
                      }
                    </div>
                    <div>
                      <p className="text-white font-medium text-sm lg:text-base">{transaction.description}</p>
                      <p className="text-gray-400 text-xs lg:text-sm">{transaction.date}</p>
                    </div>
                  </div>
                  <div className={`font-bold text-sm lg:text-lg ${
                    transaction.amount.startsWith('+') ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {transaction.amount}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

    </div>
  );
};

export default Capital;
