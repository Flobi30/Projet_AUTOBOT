import React from 'react';
import { Strategy } from '../../pages/Backtest';

interface StrategyDetailModalProps {
  strategy: Strategy;
}

const StrategyDetailModal: React.FC<StrategyDetailModalProps> = ({ strategy }) => {
  return (
    <div className="space-y-6">
      <p className="text-gray-400">{strategy.description}</p>

      <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-4">
        <h4 className="text-lg font-bold text-white mb-2">Historique de performance</h4>
        <p className="text-gray-400 text-sm">
          Non disponible depuis le backend pour cette vue. Aucun graphique simule n'est affiche.
        </p>
      </div>

      <div>
        <h4 className="text-lg font-bold text-white mb-3">Statistiques disponibles</h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="p-3 bg-gray-700/50 rounded-lg">
            <span className="text-gray-400">Performance</span>
            <div className="text-white font-bold text-xl">{strategy.performance || 'Non disponible'}</div>
          </div>
          <div className="p-3 bg-gray-700/50 rounded-lg">
            <span className="text-gray-400">Taux de reussite</span>
            <div className="text-white font-bold text-xl">{strategy.winRate || 'Non disponible'}</div>
          </div>
          <div className="p-3 bg-gray-700/50 rounded-lg">
            <span className="text-gray-400">Ratio de Sharpe</span>
            <div className="text-white font-bold text-xl">{strategy.sharpe || 'Non disponible'}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StrategyDetailModal;
