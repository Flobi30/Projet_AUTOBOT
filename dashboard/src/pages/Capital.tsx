import React, { useState, useEffect, useCallback } from 'react';
import { Wallet, DollarSign, CreditCard, TrendingUp, TrendingDown, Loader, ExternalLink, ShieldAlert } from 'lucide-react';
import MetricCard from '../components/ui/MetricCard';
import { useAppStore } from '../store/useAppStore';
import { apiFetch } from '../api/client';

interface AccountView {
  active?: boolean;
  connected?: boolean;
  total_balance?: number | null;
  available_cash?: number | null;
  eur_available?: number | null;
  balances?: Record<string, number>;
  last_sync?: string | null;
  message?: string;
}

interface CapitalData {
  total_capital: number;
  total_balance?: number;
  allocated_capital?: number;
  reserve_cash?: number;
  total_profit: number;
  total_invested: number;
  available_cash: number;
  cash_balance?: number;
  open_position_notional?: number;
  source?: string;
  source_status?: string;
  paper_mode?: boolean;
  currency: string;
  timestamp: string;
  balances?: Record<string, number>;
  paper_account?: AccountView;
  kraken_account?: AccountView;
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

interface PaperSummary {
  is_paper_mode: boolean;
  paper_instances: number;
  live_instances: number;
  pairs_tested: number;
}

const Capital: React.FC = () => {
  const { setCapitalTotal } = useAppStore();
  const [capitalData, setCapitalData] = useState<CapitalData | null>(null);
  const [paperSummary, setPaperSummary] = useState<PaperSummary | null>(null);
  const [trades, setTrades] = useState<TradeData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCapitalData = useCallback(async () => {
    try {
      setError(null);

      const [capitalRes, tradesRes, paperRes] = await Promise.all([
        apiFetch('/api/capital'),
        apiFetch('/api/trades?limit=10'),
        apiFetch('/api/paper-trading/summary'),
      ]);

      if (!capitalRes.ok) throw new Error(`API Capital indisponible: ${capitalRes.status}`);
      const data: CapitalData = await capitalRes.json();
      setCapitalData(data);
      setCapitalTotal(data.total_capital);

      if (tradesRes.ok) {
        const tradesData = await tradesRes.json();
        setTrades(tradesData.trades || []);
      } else {
        setTrades([]);
      }

      if (paperRes.ok) {
        setPaperSummary(await paperRes.json());
      } else {
        setPaperSummary(null);
      }
    } catch (err) {
      console.error('Erreur connexion API Capital:', err);
      setError(err instanceof Error ? err.message : 'Erreur de connexion');
    } finally {
      setIsLoading(false);
    }
  }, [setCapitalTotal]);

  useEffect(() => {
    fetchCapitalData();
    const interval = setInterval(fetchCapitalData, 5000);
    return () => clearInterval(interval);
  }, [fetchCapitalData]);

  const isPaperMode = capitalData?.paper_mode === true || paperSummary?.is_paper_mode === true;

  const formatCurrency = (value?: number | null): string => {
    if (typeof value !== 'number' || Number.isNaN(value)) return 'Non disponible';
    return value.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
  };

  const formatDate = (value?: string | null) => {
    if (!value) return 'Non disponible';
    return new Date(value).toLocaleString('fr-FR');
  };

  const recentTransactions = trades.map((trade) => ({
    type: trade.pnl >= 0 ? 'profit' : 'loss',
    amount: `${trade.pnl >= 0 ? '+' : ''}${formatCurrency(trade.pnl)}`,
    description: `${trade.side} ${trade.pair} (${trade.instance_name})`,
    date: formatDate(trade.timestamp),
  }));

  const balances = capitalData?.kraken_account?.balances || capitalData?.balances || {};
  const cryptoBalances = Object.entries(balances).filter(([asset, value]) => !['EUR', 'ZEUR'].includes(asset) && value !== 0);

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex items-center space-x-3 mb-3">
          <Wallet className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400" />
          <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
            Capital
          </h1>
          {isLoading && <Loader className="w-5 h-5 text-emerald-400 animate-spin" />}
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">
          Lecture du capital depuis le backend AUTOBOT. Les champs absents restent marques comme non disponibles.
        </p>
        {error && (
          <div className="mt-3 bg-red-500/20 border border-red-500/50 rounded-lg p-3 text-red-300 text-sm">
            {error}. Aucune valeur de secours n'est inventee par le dashboard.
          </div>
        )}
      </div>

      {isPaperMode && (
        <div className="mb-6 bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 flex items-start gap-3">
          <ShieldAlert className="w-6 h-6 text-amber-300 mt-0.5" />
          <div>
            <h3 className="text-amber-300 font-bold text-lg">Mode Paper Trading actif</h3>
            <p className="text-amber-200/80 text-sm">
              Le capital affiche est virtuel et persistant cote paper executor. Aucun argent reel Kraken n'est engage par AUTOBOT.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <MetricCard
          title={isPaperMode ? 'Capital paper virtuel' : 'Solde Kraken total'}
          value={formatCurrency(capitalData?.total_capital)}
          icon={<DollarSign className="w-5 h-5" />}
        />
        <MetricCard
          title="PnL realise"
          value={formatCurrency(capitalData?.total_profit)}
          icon={<TrendingUp className="w-5 h-5" />}
          isPositive={(capitalData?.total_profit ?? 0) >= 0}
          change={capitalData && capitalData.total_capital > 0
            ? `${((capitalData.total_profit / capitalData.total_capital) * 100).toFixed(2)}%`
            : undefined}
        />
        <MetricCard
          title="Capital alloue AUTOBOT"
          value={formatCurrency(capitalData?.allocated_capital ?? capitalData?.total_invested)}
          icon={<CreditCard className="w-5 h-5" />}
        />
        <MetricCard
          title="Cash disponible backend"
          value={formatCurrency(capitalData?.available_cash)}
          icon={<Wallet className="w-5 h-5" />}
        />
        <MetricCard
          title="Positions/ordres engages"
          value={formatCurrency(capitalData?.open_position_notional)}
          icon={<TrendingDown className="w-5 h-5" />}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8 mb-6 lg:mb-8">
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">Compte Kraken reel</h3>
          <div className="space-y-4 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Connexion compte</span>
              <span className={capitalData?.kraken_account?.connected ? 'text-emerald-400 font-bold' : 'text-amber-300 font-bold'}>
                {capitalData?.kraken_account?.connected ? 'Connecte' : 'Non connecte / non utilise'}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Solde total Kraken</span>
              <span className="text-white font-bold">{formatCurrency(capitalData?.kraken_account?.total_balance)}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">EUR disponible Kraken</span>
              <span className="text-white font-bold">{formatCurrency(capitalData?.kraken_account?.eur_available)}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Derniere synchro Kraken</span>
              <span className="text-white font-bold">{formatDate(capitalData?.kraken_account?.last_sync)}</span>
            </div>
            <p className="text-gray-400 border-t border-gray-700/50 pt-4">
              {capitalData?.kraken_account?.message || 'Non disponible.'}
            </p>
            <div className="pt-2">
              <p className="text-gray-400 mb-2">Soldes crypto disponibles</p>
              {cryptoBalances.length === 0 ? (
                <p className="text-gray-500">Non disponible ou aucun solde crypto expose par le backend.</p>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {cryptoBalances.map(([asset, value]) => (
                    <div key={asset} className="bg-gray-700/40 rounded-lg p-3">
                      <div className="text-gray-400 text-xs">{asset}</div>
                      <div className="text-white font-bold">{value}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">Capital paper AUTOBOT</h3>
          <div className="space-y-4 text-sm">
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Paper actif</span>
              <span className={isPaperMode ? 'text-amber-300 font-bold' : 'text-gray-400 font-bold'}>
                {isPaperMode ? 'Oui' : 'Non'}
              </span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Capital paper</span>
              <span className="text-white font-bold">{formatCurrency(capitalData?.paper_account?.total_balance)}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Cash paper disponible</span>
              <span className="text-white font-bold">{formatCurrency(capitalData?.paper_account?.available_cash)}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Strategies paper</span>
              <span className="text-white font-bold">{paperSummary?.paper_instances ?? 'Non disponible'}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-gray-400">Paires surveillees</span>
              <span className="text-white font-bold">{paperSummary?.pairs_tested ?? 'Non disponible'}</span>
            </div>
            <p className="text-gray-400 border-t border-gray-700/50 pt-4">
              {capitalData?.paper_account?.message || 'Non disponible.'}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8">
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 text-center">Actions externes</h3>
          <div className="flex flex-col gap-4">
            <a
              href="https://pro.kraken.com/app/wallets/fund"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 text-base font-semibold text-white shadow-lg shadow-emerald-500/20 transition-all hover:bg-emerald-600 no-underline"
            >
              <ExternalLink className="w-5 h-5" />
              <span>Gerer les depots/retraits sur Kraken</span>
            </a>
            <p className="text-gray-400 text-sm text-center">
              AUTOBOT ne demande pas vos identifiants Kraken et ne gere pas les depots ou retraits. Ce bouton ouvre la page officielle Kraken Pro dans un nouvel onglet.
            </p>
          </div>
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">Trades executes</h3>
          <div className="space-y-3">
            {recentTransactions.length === 0 ? (
              <div className="text-gray-500 text-center py-8">
                Bot actif mais aucune execution encore enregistree.
              </div>
            ) : (
              recentTransactions.map((transaction, index) => (
                <div key={index} className="flex flex-col sm:flex-row sm:justify-between sm:items-center p-3 lg:p-4 bg-gray-700/50 rounded-xl space-y-2 sm:space-y-0">
                  <div className="flex items-center space-x-3">
                    <div className={`w-8 lg:w-10 h-8 lg:h-10 rounded-lg flex items-center justify-center ${
                      transaction.type === 'profit' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                    }`}>
                      {transaction.type === 'profit'
                        ? <TrendingUp className="w-4 lg:w-5 h-4 lg:h-5" />
                        : <TrendingDown className="w-4 lg:w-5 h-4 lg:h-5" />}
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
