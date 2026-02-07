import React, { useState } from 'react';
import { Banknote, Loader, CheckCircle, AlertTriangle, User } from 'lucide-react';
import axios from 'axios';

const WithdrawalForm: React.FC = () => {
  const [amount, setAmount] = useState('');
  const [iban, setIban] = useState('');
  const [accountHolder, setAccountHolder] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(false);

    // --- GUIDE POUR DEVIN ---
    // Étape 1: Valider les données côté client (simple validation).
    if (parseFloat(amount) <= 0 || !iban || !accountHolder) {
      setError("Veuillez remplir tous les champs correctement.");
      setLoading(false);
      return;
    }

    // Étape 2: Envoyer la demande de retrait au backend.
    // Devin devra créer un endpoint API (ex: /api/create-payout)
    // qui gère la logique de retrait de manière sécurisée en utilisant l'API Stripe.
    // Le backend doit créer un "Payout" ou un "Transfer" vers les coordonnées bancaires fournies.
    try {
      // NOTE POUR DEVIN: Décommentez et adaptez ce code pour l'appel réel au backend.
      /*
      const response = await axios.post('/api/create-payout', {
        amount: parseFloat(amount) * 100, // Montant en centimes
        currency: 'eur',
        destination: {
          type: 'iban',
          details: iban,
        },
        accountHolderName: accountHolder,
      });

      if (response.status === 200) {
        setSuccess(true);
        setAmount('');
        setIban('');
        setAccountHolder('');
      } else {
        setError(response.data.message || "Une erreur est survenue lors du retrait.");
      }
      */
     
      // Pour la démo, on simule un succès après 1.5s.
      await new Promise(resolve => setTimeout(resolve, 1500));
      setSuccess(true);
      setAmount('');
      setIban('');
      setAccountHolder('');
      
    } catch (backendError) {
      setError("Erreur de communication avec le serveur. Le backend doit être implémenté.");
      console.error("Erreur Backend (à implémenter par Devin):", backendError);
    }
    // --- FIN DU GUIDE POUR DEVIN ---

    setLoading(false);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <label htmlFor="withdraw-amount" className="block text-sm font-medium text-gray-300 mb-2">
          Montant du retrait (€)
        </label>
        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <Banknote className="h-5 w-5 text-gray-400" />
          </div>
          <input
            id="withdraw-amount"
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="100"
            required
            className="block w-full rounded-xl border-gray-600 bg-gray-700 pl-10 pr-4 py-3 text-white shadow-sm focus:border-blue-500 focus:ring-blue-500"
          />
        </div>
      </div>
      
      <div>
        <label htmlFor="account-holder" className="block text-sm font-medium text-gray-300 mb-2">
          Nom du titulaire du compte
        </label>
        <div className="relative">
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <User className="h-5 w-5 text-gray-400" />
          </div>
          <input
            id="account-holder"
            type="text"
            value={accountHolder}
            onChange={(e) => setAccountHolder(e.target.value)}
            placeholder="John Doe"
            required
            className="block w-full rounded-xl border-gray-600 bg-gray-700 pl-10 pr-4 py-3 text-white shadow-sm focus:border-blue-500 focus:ring-blue-500"
          />
        </div>
      </div>

      <div>
        <label htmlFor="iban" className="block text-sm font-medium text-gray-300 mb-2">
          IBAN
        </label>
        <div className="relative">
          <input
            id="iban"
            type="text"
            value={iban}
            onChange={(e) => setIban(e.target.value)}
            placeholder="FR14 2004 1010 0505 0001 3M02 606"
            required
            className="block w-full rounded-xl border-gray-600 bg-gray-700 px-4 py-3 text-white shadow-sm focus:border-blue-500 focus:ring-blue-500"
          />
        </div>
      </div>
      
      {error && (
        <div className="flex items-center space-x-2 text-red-400 bg-red-500/10 p-3 rounded-lg">
          <AlertTriangle className="h-5 w-5" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="flex items-center space-x-2 text-emerald-400 bg-emerald-500/10 p-3 rounded-lg">
          <CheckCircle className="h-5 w-5" />
          <span>Demande de retrait initiée. Traitement en cours.</span>
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        className="w-full flex justify-center items-center space-x-2 rounded-xl bg-blue-500 px-4 py-3 text-base font-semibold text-white shadow-lg shadow-blue-500/20 transition-all hover:bg-blue-600 disabled:bg-gray-600 disabled:cursor-not-allowed"
      >
        {loading ? (
          <Loader className="h-5 w-5 animate-spin" />
        ) : (
          <Banknote className="h-5 w-5" />
        )}
        <span>{loading ? 'Traitement...' : `Retirer ${amount ? amount + '€' : ''}`}</span>
      </button>
      
      <p className="text-center text-xs text-gray-500">
        Les retraits sont généralement traités sous 2-3 jours ouvrés.
      </p>
    </form>
  );
};

export default WithdrawalForm;
