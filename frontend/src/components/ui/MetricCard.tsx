import React from 'react';

interface MetricCardProps {
  title: string;
  value: string;
  change?: string;
  isPositive?: boolean;
  icon?: React.ReactNode;
}

const MetricCard: React.FC<MetricCardProps> = ({ title, value, change, isPositive = true, icon }) => {
  return (
    <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-xl p-6 hover:shadow-lg hover:shadow-emerald-500/10 transition-all duration-200 group">
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center space-x-2">
          {icon && <div className="text-emerald-400">{icon}</div>}
          <span className="text-gray-400 text-sm font-medium">{title}</span>
        </div>
        {change && (
          <span className={`text-sm font-bold px-2 py-1 rounded-lg ${
            isPositive 
              ? 'text-emerald-400 bg-emerald-500/10' 
              : 'text-red-400 bg-red-500/10'
          }`}>
            {change}
          </span>
        )}
      </div>
      <div className="text-3xl font-bold text-white group-hover:text-emerald-400 transition-colors">
        {value}
      </div>
    </div>
  );
};

export default MetricCard;
