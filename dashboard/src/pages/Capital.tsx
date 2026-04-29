import React, { useState, useEffect, useCallback } from 'react';
import { Wallet, TrendingUp, TrendingDown, Loader, ExternalLink, ShieldAlert } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { apiFetch } from '../api/client';

interface AccountView {
  active?: boolean;
  connected?: boolean;
  total_balance?: number | null;
  trading_capital?: number | null;
  available_cash?: number | null;
  reference_capital?: number | null;
  unallocated_reserve?: number | null;
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
  autobot_trading_capital?: number | null;
  autobot_available_capital?: number | null;
  paper_reference_capital?: number | null;
  paper_historical_balance?: number | null;
  paper_unallocated_reserve?: number | null;
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
      setCapitalTotal(data.autobot_trading_capital ?? data.allocated_capital ?? data.total_capital);

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

  const paperTradingCapital = (
    capitalData?.paper_account?.trading_capital
    ?? capitalData?.autobot_trading_capital
    ?? (isPaperMode ? capitalData?.total_capital : null)
  );
  const paperAvailable = (
    capitalData?.paper_account?.available_cash
    ?? capitalData?.autobot_available_capital
    ?? (isPaperMode ? capitalData?.available_cash : null)
  );
  const paperEngaged = isPaperMode ? capitalData?.open_position_notional : null;
  const paperPnl = isPaperMode ? capitalData?.total_profit : null;

  const realTotal = capitalData?.kraken_account?.total_balance ?? (!isPaperMode ? capitalData?.total_capital : null);
  const realCash = (
    capitalData?.kraken_account?.eur_available
    ?? capitalData?.kraken_account?.available_cash
    ?? (!isPaperMode ? capitalData?.available_cash : null)
  );
  const realUsedByAutobot = isPaperMode ? 0 : (capitalData?.allocated_capital ?? capitalData?.total_invested ?? null);
  const realPnl = isPaperMode ? null : capitalData?.total_profit;

  const renderCapitalTable = (
    title: string,
    subtitle: string,
    rows: Array<{ label: string; value: React.ReactNode; hint?: string }>
  ) => (
    <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-6 shadow-2xl">
      <div className="mb-4">
        <h3 className="text-xl font-bold text-emerald-400">{title}</h3>
        <p className="text-gray-400 text-sm mt-1">{subtitle}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <tbody className="divide-y divide-gray-700/70">
            {rows.map((row) => (
              <tr key={row.label}>
                <td className="py-3 pr-4 text-gray-400 align-top">{row.label}</td>
                <td className="py-3 text-right align-top">
                  <div className="text-white font-semibold">{row.value}</div>
                  {row.hint && <div className="text-gray-500 text-xs mt-1">{row.hint}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

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
              Le capital affiche est le budget virtuel actif d'AUTOBOT. Aucun argent reel Kraken n'est engage.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8 mb-6 lg:mb-8">
        {renderCapitalTable(
          'Paper',
          'Budget virtuel actif utilise pour entrainer AUTOBOT.',
          [
            { label: 'Statut', value: isPaperMode ? 'Actif' : 'Inactif' },
            {
              label: 'Capital paper actif',
              value: formatCurrency(paperTradingCapital),
              hint: 'Capital virtuel actuellement pilote par AUTOBOT.',
            },
            {
              label: 'PnL paper realise',
              value: (
                <span className={(paperPnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                  {formatCurrency(paperPnl)}
                </span>
              ),
            },
            {
              label: 'Positions / ordres engages',
              value: formatCurrency(paperEngaged),
              hint: 'Part du capital paper deja immobilisee par des positions ou ordres ouverts.',
            },
            {
              label: 'Libre pour nouvelles positions',
              value: formatCurrency(paperAvailable),
              hint: 'Part du capital paper actif non engagee pour le moment.',
            },
            { label: 'Strategies / paires', value: `${paperSummary?.paper_instances ?? 'Non disponible'} / ${paperSummary?.pairs_tested ?? 'Non disponible'}` },
          ]
        )}

        {renderCapitalTable(
          'Reel',
          'Compte Kraken et capital live. En paper, AUTOBOT ne l utilise pas.',
          [
            {
              label: 'Connexion Kraken',
              value: capitalData?.kraken_account?.connected ? 'Connecte' : 'Non connecte / non utilise',
            },
            { label: 'Solde reel Kraken', value: formatCurrency(realTotal) },
            { label: 'Cash reel EUR disponible', value: formatCurrency(realCash) },
            {
              label: 'Capital reel utilise par AUTOBOT',
              value: formatCurrency(realUsedByAutobot),
              hint: isPaperMode ? '0 euro engage tant que le mode paper est actif.' : undefined,
            },
            {
              label: 'PnL reel realise',
              value: isPaperMode ? 'Non utilise en paper' : formatCurrency(realPnl),
            },
            { label: 'Derniere synchro Kraken', value: formatDate(capitalData?.kraken_account?.last_sync) },
          ]
        )}
      </div>

      {cryptoBalances.length > 0 && (
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-6 shadow-2xl mb-6 lg:mb-8">
          <h3 className="text-xl font-bold text-emerald-400 mb-4">Soldes crypto reels Kraken</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {cryptoBalances.map(([asset, value]) => (
              <div key={asset} className="bg-gray-700/40 rounded-lg p-3">
                <div className="text-gray-400 text-xs">{asset}</div>
                <div className="text-white font-bold">{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

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
