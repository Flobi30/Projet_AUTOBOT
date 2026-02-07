import React from 'react';
import { motion } from 'framer-motion';
import { Info, BrainCircuit, Zap, ShieldAlert } from 'lucide-react';

type LogLevel = 'INFO' | 'STRATEGY' | 'TRADE' | 'RISK';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
}

const logConfig = {
  INFO: { icon: Info, color: 'text-blue-400' },
  STRATEGY: { icon: BrainCircuit, color: 'text-purple-400' },
  TRADE: { icon: Zap, color: 'text-emerald-400' },
  RISK: { icon: ShieldAlert, color: 'text-yellow-400' },
};

const mockLogs: LogEntry[] = [
  { timestamp: '14:35:10', level: 'RISK', message: 'Stop-loss ajusté pour la position ETH/USD.' },
  { timestamp: '14:33:02', level: 'TRADE', message: 'Ordre d\'achat de 0.15 BTC exécuté à 46,150€.' },
  { timestamp: '14:32:48', level: 'STRATEGY', message: 'Activation de la stratégie "Scalping Volatilité".' },
  { timestamp: '14:32:15', level: 'INFO', message: 'Nouvelle analyse du marché BTC/USD en cours...' },
  { timestamp: '14:31:05', level: 'INFO', message: 'Connexion à l\'API de trading établie.' },
];

const LiveLog: React.FC = () => {
  return (
    <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
      <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
        <Info className="w-5 lg:w-6 h-5 lg:h-6" />
        <span>Journal d'Activité du Bot</span>
      </h3>
      <div className="h-96 overflow-y-auto pr-2 space-y-4">
        {mockLogs.map((log, index) => {
          const Icon = logConfig[log.level].icon;
          const color = logConfig[log.level].color;
          return (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
              className="flex items-start space-x-3 text-sm"
            >
              <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${color}`} />
              <div className="flex-1">
                <span className="font-mono text-gray-500 mr-2">{log.timestamp}</span>
                <span className={`font-bold mr-2 ${color}`}>[{log.level}]</span>
                <span className="text-gray-300">{log.message}</span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
};

export default LiveLog;
