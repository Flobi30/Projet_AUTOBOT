import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ExternalLink, Landmark, RefreshCw, ShieldCheck, WalletCards } from 'lucide-react';
import { apiFetch } from '../api/client';

type AccountView = {
  connected?: boolean;
  total_balance?: number | null;
  available_cash?: number | null;
  eur_available?: number | null;
  last_sync?: string | null;
  message?: string | null;
};

type CapitalResponse = {
  paper_mode?: boolean;
  source_status?: string;
  total_capital?: number | null;
  available_cash?: number | null;
  autobot_trading_capital?: number | null;
  kraken_account?: AccountView | null;
};

const KRAKEN_PRO_FUNDING_URL = 'https://pro.kraken.com/app/wallets/fund';
const KRAKEN_PRO_WITHDRAW_HELP_URL = 'https://support.kraken.com/hc/en-us/articles/7203077726740-How-to-withdraw-funds-from-your-Kraken-account';
const KRAKEN_APP_FUNDING_HELP_URL = 'https://support.kraken.com/hc/en-us/articles/360058699052-Depositing-and-withdrawing-funds-from-the-Kraken-app';

const formatCurrency = (value?: number | null) =>
  typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })
    : 'Non disponible';

const formatDate = (value?: string | null) => {
  if (!value) return 'Non disponible';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Non disponible' : date.toLocaleString('fr-FR');
};

const Row: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="flex items-start justify-between gap-4 border-b border-gray-700/60 py-3 last:border-0">
    <span className="text-sm text-gray-400">{label}</span>
    <span className="max-w-[55%] text-right text-sm font-semibold text-white">{value}</span>
  </div>
);

const Funding: React.FC = () => {
  const [capital, setCapital] = useState<CapitalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const response = await apiFetch('/api/capital');
      if (!response.ok) throw new Error(`API capital indisponible: ${response.status}`);
      setCapital(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur API');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 60000);
    return () => clearInterval(interval);
  }, [refresh]);

  const paperMode = capital?.paper_mode !== false;
  const kraken = capital?.kraken_account ?? null;
  const realTotal = kraken?.total_balance ?? (paperMode ? null : capital?.total_capital);
  const realEur = kraken?.eur_available ?? kraken?.available_cash ?? (paperMode ? null : capital?.available_cash);

  return (
    <div className="min-h-screen bg-gray-900 p-4 sm:p-6 lg:p-8">
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Landmark className="h-7 w-7 text-emerald-300" />
            <h1 className="text-2xl font-bold text-white">Depots / Retraits Kraken</h1>
          </div>
          <p className="mt-1 text-sm text-gray-400">AUTOBOT ouvre Kraken, il ne manipule pas les fonds depuis le dashboard.</p>
        </div>
        <button
          onClick={refresh}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-gray-700 bg-gray-800 px-4 text-sm font-medium text-gray-200 hover:bg-gray-700"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Actualiser
        </button>
      </div>

      {error ? (
        <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {error}. Aucune valeur de secours n'est inventee.
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <section className="rounded-lg border border-gray-700 bg-gray-800 p-5">
          <div className="mb-4 flex items-center gap-2 text-white">
            <WalletCards className="h-5 w-5 text-emerald-300" />
            <h2 className="text-base font-semibold">Etat du compte</h2>
          </div>
          <Row label="Mode AUTOBOT" value={paperMode ? 'PAPER' : 'LIVE'} />
          <Row label="Capital AUTOBOT" value={formatCurrency(capital?.autobot_trading_capital ?? capital?.total_capital)} />
          <Row label="Kraken connecte" value={kraken?.connected ? 'Oui' : 'Non / non utilise'} />
          <Row label="Solde reel Kraken" value={formatCurrency(realTotal)} />
          <Row label="EUR disponible Kraken" value={formatCurrency(realEur)} />
          <Row label="Derniere synchro" value={formatDate(kraken?.last_sync)} />
        </section>

        <section className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-5">
          <div className="mb-4 flex items-center gap-2 text-white">
            <ExternalLink className="h-5 w-5 text-emerald-300" />
            <h2 className="text-base font-semibold">Action officielle</h2>
          </div>
          <a
            href={KRAKEN_PRO_FUNDING_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-emerald-500 px-4 py-3 text-sm font-semibold text-white no-underline shadow-lg shadow-emerald-500/20 hover:bg-emerald-600"
          >
            Gerer les depots/retraits sur Kraken
            <ExternalLink className="h-4 w-4" />
          </a>
          <div className="mt-4 grid grid-cols-1 gap-2 text-sm">
            <a className="text-emerald-200 underline-offset-4 hover:underline" href={KRAKEN_PRO_WITHDRAW_HELP_URL} target="_blank" rel="noopener noreferrer">
              Guide retrait Kraken Pro
            </a>
            <a className="text-emerald-200 underline-offset-4 hover:underline" href={KRAKEN_APP_FUNDING_HELP_URL} target="_blank" rel="noopener noreferrer">
              Guide depots/retraits Kraken
            </a>
          </div>
        </section>

        <section className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-5">
          <div className="mb-4 flex items-center gap-2 text-white">
            <ShieldCheck className="h-5 w-5 text-amber-300" />
            <h2 className="text-base font-semibold">Securite</h2>
          </div>
          <div className="space-y-3 text-sm text-amber-100/90">
            <div className="flex gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Les identifiants Kraken restent uniquement chez Kraken.</span>
            </div>
            <div className="flex gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Le dashboard ne cree jamais de retrait automatiquement.</span>
            </div>
            <div className="flex gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Une cle API de trading ne devrait pas avoir la permission Withdraw.</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default Funding;
