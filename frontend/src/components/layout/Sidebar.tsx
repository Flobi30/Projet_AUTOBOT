import React from 'react';
import { NavLink } from 'react-router-dom';
import { TrendingUp, BarChart3, Wallet, PieChart, Bot, User, Activity, Menu, X } from 'lucide-react';

interface SidebarProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ isOpen, setIsOpen }) => {
  const navItems = [
    {
      category: 'TRADING & ANALYSE',
      items: [
        { name: 'Live Trading', path: '/trading', icon: TrendingUp },
        { name: 'Backtest', path: '/backtest', icon: BarChart3 },
      ]
    },
    {
      category: 'GESTION',
      items: [
        { name: 'Capital', path: '/capital', icon: Wallet },
        { name: 'Analytics', path: '/analytics', icon: PieChart },
      ]
    }
  ];

  return (
    <>
      {/* Mobile Menu Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="lg:hidden fixed top-4 left-4 z-50 bg-gray-800 text-white p-2 rounded-xl border border-gray-700 shadow-lg"
      >
        {isOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
      </button>

      {/* Mobile Overlay */}
      {isOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-40"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Sidebar */}
      <div className={`
        fixed left-0 top-0 h-screen w-64 bg-gray-800 border-r border-gray-700 shadow-2xl z-50 transform transition-transform duration-300 ease-in-out
        ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        lg:translate-x-0
      `}>
        {/* Logo Header */}
        <div className="p-6 border-b border-gray-700 bg-gradient-to-r from-gray-800 to-gray-750">
          <div className="flex items-center space-x-4">
            {/* Logo Container */}
            <div className="w-12 h-12 bg-gradient-to-br from-emerald-400 to-emerald-600 rounded-xl flex items-center justify-center shadow-lg">
              <Bot className="w-7 h-7 text-white" />
              {/* Ou utilisez votre logo : <img src="/path/to/your/logo.png" alt="AUTOBOT" className="w-8 h-8" /> */}
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">AUTOBOT</h1>
              <div className="flex items-center space-x-1 mt-1">
                <div className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></div>
                <span className="text-emerald-400 text-xs font-medium">LIVE</span>
              </div>
            </div>
          </div>
        </div>

        {/* Navigation */}
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
                    onClick={() => setIsOpen(false)} // Ferme le menu sur mobile après clic
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

        {/* Status & User Profile */}
        <div className="p-4 border-t border-gray-700 bg-gray-800/50">
          {/* Bot Status */}
          <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Activity className="w-4 h-4 text-emerald-400" />
                <span className="text-emerald-400 text-sm font-medium">Bot Status</span>
              </div>
              <span className="text-emerald-400 text-sm font-bold">ACTIF</span>
            </div>
            <div className="mt-1 text-xs text-emerald-300">
              Performance: +8.42% • 24/7
            </div>
          </div>

          {/* User Profile */}
          <div className="flex items-center space-x-3 p-2 rounded-lg hover:bg-gray-700 transition-colors cursor-pointer">
            <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-emerald-600 rounded-full flex items-center justify-center shadow-md">
              <User className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-medium text-white">Trader Pro</div>
              <div className="text-xs text-gray-400">Compte Premium</div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default Sidebar;
