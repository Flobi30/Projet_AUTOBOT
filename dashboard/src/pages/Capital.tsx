import React, { useState } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import { Wallet, DollarSign, CreditCard, TrendingUp, TrendingDown, Banknote, Loader } from 'lucide-react';
import MetricCard from '../components/ui/MetricCard';
import WithdrawalForm from '../components/ui/WithdrawalForm';
import Modal from '../components/ui/Modal';
import axios from 'axios';

// Chargez votre clé publique Stripe depuis les variables d'environnement
const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLIC_KEY);

const Capital: React.FC = () => {
  const [isWithdrawalModalOpen, setIsWithdrawalModalOpen] = useState(false);
  const [isDepositLoading, setIsDepositLoading] = useState(false);

  const handleDepositClick = async () => {
    setIsDepositLoading(true);

    // --- GUIDE POUR DEVIN ---
    // Étape 1: Appeler votre backend pour créer une session de Checkout Stripe.
    // Vous devez créer un endpoint (ex: POST /api/create-checkout-session)
    // qui utilise la bibliothèque Stripe Node.js pour créer une session.
    // Il doit retourner un { sessionId: 'cs_...' }.
    try {
      // NOTE POUR DEVIN: Décommentez et adaptez ce code pour l'appel réel au backend.
      /*
      const response = await axios.post('/api/create-checkout-session', {
        amount: 5000, // Montant en centimes, ex: 50.00€
        currency: 'eur',
      });
      const { sessionId } = response.data;
      */

      // Simulation pour la démo. Devin remplacera ceci.
      await new Promise(resolve => setTimeout(resolve, 1500));
      const sessionId = 'cs_test_...'; // Ceci est un ID de session factice.
      console.log("DEVIN: Session de Checkout créée sur le backend avec l'ID:", sessionId);
      alert("Redirection vers Stripe Checkout simulée. Devin doit implémenter l'appel backend pour que cela fonctionne réellement.");

      // Étape 2: Rediriger l'utilisateur vers la page de paiement Stripe.
      const stripe = await stripePromise;
      if (stripe && sessionId !== 'cs_test_...') { // Ne pas rediriger avec le faux ID
        const { error } = await stripe.redirectToCheckout({ sessionId });
        if (error) {
          console.error("Erreur de redirection Stripe:", error.message);
          // Gérer l'erreur côté client ici
        }
      }
    } catch (error) {
      console.error("Erreur lors de la création de la session de Checkout:", error);
      alert("Le backend pour créer la session de paiement n'est pas encore implémenté.");
    }
    // --- FIN DU GUIDE POUR DEVIN ---

    setIsDepositLoading(false);
  };
  
  const recentTransactions = [
    { type: 'deposit', amount: '+1,500€', description: 'Dépôt par carte', date: '23/01/2025' },
    { type: 'profit', amount: '+127€', description: 'Profit trading BTC/USD', date: '22/01/2025' },
    { type: 'withdraw', amount: '-300€', description: 'Retrait vers compte bancaire', date: '20/01/2025' },
  ];

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      {/* Header */}
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex items-center space-x-3 mb-3">
          <Wallet className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400" />
          <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
            Portail Capital
          </h1>
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">Gérez vos fonds de manière sécurisée.</p>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <MetricCard title="Capital Total" value="5,420€" icon={<DollarSign className="w-5 h-5" />} />
        <MetricCard title="Profit Réalisé" value="1,285€" icon={<TrendingUp className="w-5 h-5" />} />
        <MetricCard title="Capital Investi" value="4,135€" icon={<CreditCard className="w-5 h-5" />} />
        <MetricCard title="Cash Disponible" value="285€" icon={<Wallet className="w-5 h-5" />} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 lg:gap-8">
        {/* Actions Module */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl flex flex-col justify-center">
            <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 text-center">Actions Rapides</h3>
            <div className="flex flex-col sm:flex-row gap-4">
                <button 
                    onClick={handleDepositClick}
                    disabled={isDepositLoading}
                    className="flex-1 flex items-center justify-center space-x-2 rounded-xl bg-emerald-500 px-4 py-3 text-base font-semibold text-white shadow-lg shadow-emerald-500/20 transition-all hover:bg-emerald-600 disabled:bg-gray-600 disabled:cursor-not-allowed"
                >
                    {isDepositLoading ? <Loader className="w-5 h-5 animate-spin" /> : <CreditCard className="w-5 h-5" />}
                    <span>{isDepositLoading ? 'Préparation...' : 'Effectuer un Dépôt'}</span>
                </button>
                <button 
                    onClick={() => setIsWithdrawalModalOpen(true)}
                    className="flex-1 flex items-center justify-center space-x-2 rounded-xl bg-blue-500 px-4 py-3 text-base font-semibold text-white shadow-lg shadow-blue-500/20 transition-all hover:bg-blue-600"
                >
                    <Banknote className="w-5 h-5" />
                    <span>Faire un Retrait</span>
                </button>
            </div>
        </div>

        {/* Recent Transactions */}
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
          <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">Historique des Transactions</h3>
          <div className="space-y-3">
            {recentTransactions.map((transaction, index) => (
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
            ))}
          </div>
        </div>
      </div>

      {/* Withdrawal Modal */}
      <Modal isOpen={isWithdrawalModalOpen} onClose={() => setIsWithdrawalModalOpen(false)} title="Demande de Retrait">
        <WithdrawalForm />
      </Modal>
    </div>
  );
};

export default Capital;
