import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Info, BrainCircuit, Zap, ShieldAlert } from 'lucide-react';
import { apiFetch } from '../../api/client';

type LogLevel = 'INFO' | 'STRATEGY' | 'TRADE' | 'RISK';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
}

interface RuntimeTrace {
  trace?: {
    last_market_tick?: Record<string, unknown> | null;
    last_signal?: Record<string, unknown> | null;
    last_decision?: Record<string, unknown> | null;
    last_order?: Record<string, unknown> | null;
    last_trade?: Record<string, unknown> | null;
    last_error?: Record<string, unknown> | null;
  };
  messages?: string[];
}

const logConfig = {
  INFO: { icon: Info, color: 'text-blue-400' },
  STRATEGY: { icon: BrainCircuit, color: 'text-purple-400' },
  TRADE: { icon: Zap, color: 'text-emerald-400' },
  RISK: { icon: ShieldAlert, color: 'text-yellow-400' },
};

const eventTimestamp = (event?: Record<string, unknown> | null) =>
  typeof event?.timestamp === 'string' ? event.timestamp : new Date().toISOString();

const describeEvent = (label: string, event?: Record<string, unknown> | null): string | null => {
  if (!event) return null;
  const symbol = typeof event.symbol === 'string' ? event.symbol : null;
  const action = typeof event.event === 'string' ? event.event : null;
  const reason = typeof event.reason === 'string' ? event.reason : null;
  return [label, symbol, action, reason].filter(Boolean).join(' - ');
};

const LiveLog: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);

  useEffect(() => {
    const fetchRuntimeLog = async () => {
      try {
        const response = await apiFetch('/api/runtime/trace');
        if (!response.ok) {
          setLogs([]);
          return;
        }
        const data: RuntimeTrace = await response.json();
        const nextLogs: LogEntry[] = [];
        const tick = describeEvent('Dernier tick marche', data.trace?.last_market_tick);
        if (tick) nextLogs.push({ timestamp: eventTimestamp(data.trace?.last_market_tick), level: 'INFO', message: tick });
        const signal = describeEvent('Dernier signal', data.trace?.last_signal);
        if (signal) nextLogs.push({ timestamp: eventTimestamp(data.trace?.last_signal), level: 'STRATEGY', message: signal });
        const decision = describeEvent('Derniere decision', data.trace?.last_decision);
        if (decision) nextLogs.push({ timestamp: eventTimestamp(data.trace?.last_decision), level: 'RISK', message: decision });
        const order = describeEvent('Dernier ordre', data.trace?.last_order);
        if (order) nextLogs.push({ timestamp: eventTimestamp(data.trace?.last_order), level: 'TRADE', message: order });
        const trade = describeEvent('Dernier trade execute', data.trace?.last_trade);
        if (trade) nextLogs.push({ timestamp: eventTimestamp(data.trace?.last_trade), level: 'TRADE', message: trade });
        const error = describeEvent('Derniere erreur', data.trace?.last_error);
        if (error) nextLogs.push({ timestamp: eventTimestamp(data.trace?.last_error), level: 'RISK', message: error });
        (data.messages || []).forEach((message) => {
          nextLogs.push({ timestamp: new Date().toISOString(), level: 'INFO', message });
        });
        setLogs(nextLogs);
      } catch {
        setLogs([]);
      }
    };

    fetchRuntimeLog();
    const interval = setInterval(fetchRuntimeLog, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 shadow-2xl">
      <h3 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6 flex items-center space-x-2">
        <Info className="w-5 lg:w-6 h-5 lg:h-6" />
        <span>Journal runtime</span>
      </h3>
      <div className="h-96 overflow-y-auto pr-2 space-y-4">
        {logs.length === 0 ? (
          <div className="text-gray-500 text-center py-8">Journal non disponible depuis le backend.</div>
        ) : logs.map((log, index) => {
          const Icon = logConfig[log.level].icon;
          const color = logConfig[log.level].color;
          return (
            <motion.div
              key={`${log.timestamp}-${index}`}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
              className="flex items-start space-x-3 text-sm"
            >
              <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${color}`} />
              <div className="flex-1">
                <span className="font-mono text-gray-500 mr-2">
                  {new Date(log.timestamp).toLocaleTimeString('fr-FR')}
                </span>
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
