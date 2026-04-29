import React, { useCallback, useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { Wallet, Bot, Activity, Menu, X, HeartPulse, ShieldCheck } from 'lucide-react';
import { apiFetch } from '../../api/client';

interface SidebarProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
}

interface SidebarStatus {
  running: boolean;
  instance_count: number;
  websocket_connected: boolean;
}

interface SidebarCapital {
  total_capital: number;
  available_cash: number;
  autobot_trading_capital?: number | null;
  autobot_available_capital?: number | null;
  paper_unallocated_reserve?: number | null;
  paper_mode: boolean;
  source: string;
  source_status: string;
}

interface RuntimeTrace {
  overall_status: 'healthy' | 'warning' | 'critical';
  strategies?: {
    active_count: number;
    pairs_watched: string[];
  };
  safety?: {
    kill_switch?: {
      status?: string;
      tripped?: boolean;
      reason_code?: string | null;
    };
  };
}

interface SidebarColony {
  runtime?: {
    active_children_count?: number;
    child_count?: number;
    routing_symbol_count?: number;
    unassigned_symbol_count?: number;
  };
  execution?: {
    execution_mode?: string;
    auto_scale_paper_children?: boolean;
  };
}

const formatCurrency = (value?: number) =>
  typeof value === 'number'
    ? value.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })
    : 'Non disponible';

const Sidebar: React.FC<SidebarProps> = ({ isOpen, setIsOpen }) => {
  const [status, setStatus] = useState<SidebarStatus | null>(null);
  const [capital, setCapital] = useState<SidebarCapital | null>(null);
  const [trace, setTrace] = useState<RuntimeTrace | null>(null);
  const [colony, setColony] = useState<SidebarColony | null>(null);

  const fetchSidebarState = useCallback(async () => {
    try {
      const [statusRes, capitalRes, traceRes, colonyRes] = await Promise.all([
        apiFetch('/api/status'),
        apiFetch('/api/capital'),
        apiFetch('/api/runtime/trace'),
        apiFetch('/api/colony'),
      ]);
      if (statusRes.ok) setStatus(await statusRes.json());
      if (capitalRes.ok) setCapital(await capitalRes.json());
      if (traceRes.ok) setTrace(await traceRes.json());
      if (colonyRes.ok) setColony(await colonyRes.json());
    } catch {
      // Keep the last known state; page-level panels show detailed API errors.
    }
  }, []);

  useEffect(() => {
    fetchSidebarState();
    const interval = setInterval(fetchSidebarState, 15000);
    return () => clearInterval(interval);
  }, [fetchSidebarState]);

  const navItems = [
    {
      category: 'TRADING',
      items: [
        { name: 'Performance', path: '/performance', icon: Activity },
      ],
    },
    {
      category: 'GESTION',
      items: [
        { name: 'Capital', path: '/capital', icon: Wallet },
      ],
    },
    {
      category: 'SYSTEME',
      items: [
        { name: 'Diagnostic', path: '/diagnostic', icon: HeartPulse },
      ],
    },
  ];

  const modeLabel = capital ? (capital.paper_mode ? 'PAPER' : 'LIVE') : 'INCONNU';
  const botRunning = status?.running === true;
  const displayedCapital = capital?.autobot_trading_capital ?? capital?.total_capital;
  const displayedAvailable = capital?.autobot_available_capital ?? capital?.available_cash;
  const overall = trace?.overall_status ?? (botRunning ? 'healthy' : 'warning');
  const accent =
    overall === 'critical'
      ? 'red'
      : overall === 'warning'
        ? 'amber'
        : botRunning
          ? 'emerald'
          : 'gray';
  const color = {
    emerald: {
      card: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
      text: 'text-emerald-400',
      dot: 'bg-emerald-400',
    },
    amber: {
      card: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
      text: 'text-amber-400',
      dot: 'bg-amber-400',
    },
    red: {
      card: 'border-red-500/30 bg-red-500/10 text-red-300',
      text: 'text-red-400',
      dot: 'bg-red-400',
    },
    gray: {
      card: 'border-gray-600 bg-gray-700/40 text-gray-300',
      text: 'text-gray-400',
      dot: 'bg-gray-400',
    },
  }[accent];

  return (
    <>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="lg:hidden fixed top-4 left-4 z-50 bg-gray-800 text-white p-2 rounded-xl border border-gray-700 shadow-lg"
        aria-label="Ouvrir le menu"
      >
        {isOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
      </button>

      {isOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-40"
          onClick={() => setIsOpen(false)}
        />
      )}

      <div className={`
        fixed left-0 top-0 h-screen w-64 bg-gray-800 border-r border-gray-700 shadow-2xl z-50 transform transition-transform duration-300 ease-in-out
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        lg:translate-x-0
      `}>
        <div className="p-6 border-b border-gray-700 bg-gradient-to-r from-gray-800 to-gray-750">
          <div className="flex items-center space-x-4">
            <div className="w-12 h-12 bg-gradient-to-br from-emerald-400 to-emerald-600 rounded-xl flex items-center justify-center shadow-lg">
              <Bot className="w-7 h-7 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">AUTOBOT</h1>
              <div className="flex items-center space-x-1 mt-1">
                <div className={`w-2 h-2 ${color.dot} rounded-full ${botRunning ? 'animate-pulse' : ''}`} />
                <span className={`${color.text} text-xs font-medium`}>{modeLabel}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-4">
          {navItems.map((category, categoryIndex) => (
            <div key={categoryIndex} className="px-4 mb-6">
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4 px-4 border-l-2 border-emerald-500/50">
                {category.category}
              </h3>
              <nav className="space-y-2">
                {category.items.map((item) => (
                  <NavLink
                    key={item.name}
                    to={item.path}
                    onClick={() => setIsOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200 group ${
                        isActive
                          ? 'bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-500/30'
                          : 'text-gray-300 hover:bg-gray-700 hover:text-white hover:shadow-md'
                      }`
                    }
                  >
                    <item.icon className="mr-3 h-5 w-5 group-hover:scale-110 transition-transform" />
                    {item.name}
                  </NavLink>
                ))}
              </nav>
            </div>
          ))}
        </div>

        <div className="p-4 border-t border-gray-700 bg-gray-800/50">
          <div className={`mb-4 p-3 border rounded-lg ${color.card}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Activity className="w-4 h-4" />
                <span className="text-sm font-medium">Etat AUTOBOT</span>
              </div>
              <span className="text-sm font-bold">{botRunning ? 'ACTIF' : 'INACTIF'}</span>
            </div>
            <div className="mt-2 space-y-1 text-xs">
              <div>Mode: <strong>{modeLabel}</strong></div>
              <div>Capital AUTOBOT: <strong>{formatCurrency(displayedCapital)}</strong></div>
              <div>Disponible: <strong>{formatCurrency(displayedAvailable)}</strong></div>
              {capital?.paper_mode ? (
                <div>Reserve paper: <strong>{formatCurrency(capital?.paper_unallocated_reserve)}</strong></div>
              ) : null}
              <div>
                Strategies: <strong>{trace?.strategies?.active_count ?? status?.instance_count ?? 'Non disponible'}</strong>
              </div>
              <div>
                Kill switch:{' '}
                <strong className={trace?.safety?.kill_switch?.tripped ? 'text-red-300' : undefined}>
                  {trace?.safety?.kill_switch?.status ?? 'Non disponible'}
                </strong>
                {trace?.safety?.kill_switch?.reason_code ? (
                  <span> ({trace.safety.kill_switch.reason_code})</span>
                ) : null}
              </div>
              <div>
                Moteurs paper: <strong>{colony?.runtime?.active_children_count ?? 'Non disponible'}</strong>
                {typeof colony?.runtime?.child_count === 'number' ? <span> / {colony.runtime.child_count}</span> : null}
              </div>
              <div>
                Routage: <strong>{colony?.runtime?.routing_symbol_count ?? 'Non disponible'}</strong>
                {typeof colony?.runtime?.unassigned_symbol_count === 'number' && colony.runtime.unassigned_symbol_count > 0 ? (
                  <span className="text-amber-300"> ({colony.runtime.unassigned_symbol_count} non assignees)</span>
                ) : null}
              </div>
              {trace?.strategies?.pairs_watched?.length ? (
                <div>Paires: <strong>{trace.strategies.pairs_watched.join(', ')}</strong></div>
              ) : null}
            </div>
          </div>

          <div className="flex items-center space-x-3 p-2 rounded-lg bg-gray-700/40">
            <div className="w-10 h-10 bg-gray-700 rounded-full flex items-center justify-center shadow-md">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <div className="text-sm font-medium text-white">Dashboard backend</div>
              <div className="text-xs text-gray-400">
                {capital?.paper_mode ? 'Paper trading virtuel' : 'Lecture compte Kraken'}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default Sidebar;
