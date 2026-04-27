import React from 'react';
import { ExternalLink, ShieldAlert } from 'lucide-react';

const WithdrawalForm: React.FC = () => {
  return (
    <div className="space-y-6 rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6">
      <div className="flex items-start gap-3">
        <ShieldAlert className="h-6 w-6 text-amber-300 mt-0.5" />
        <div>
          <h3 className="text-lg font-bold text-amber-300">Retraits non geres par AUTOBOT</h3>
          <p className="text-sm text-amber-200/80 mt-1">
            Le dashboard ne collecte pas d'IBAN, d'identifiants Kraken ou de demande de retrait. Utilisez Kraken directement pour toute operation de depot ou retrait.
          </p>
        </div>
      </div>

      <a
        href="https://pro.kraken.com/app/wallets/fund"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-3 text-base font-semibold text-white shadow-lg shadow-emerald-500/20 transition-all hover:bg-emerald-600 no-underline"
      >
        <ExternalLink className="h-5 w-5" />
        Gerer les depots/retraits sur Kraken
      </a>
    </div>
  );
};

export default WithdrawalForm;
