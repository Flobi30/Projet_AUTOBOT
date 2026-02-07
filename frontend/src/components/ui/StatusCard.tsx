import React from 'react';

interface StatusCardProps {
  title: string;
  description: string;
  status?: 'active' | 'inactive' | 'pending';
  icon?: React.ReactNode;
}

const StatusCard: React.FC<StatusCardProps> = ({ title, description, status = 'active', icon }) => {
  const statusConfig = {
    active: {
      bg: 'bg-gradient-to-r from-emerald-500/20 to-emerald-600/20',
      border: 'border-emerald-500/50',
      pulse: 'animate-pulse',
      dot: 'bg-emerald-400'
    },
    inactive: {
      bg: 'bg-gradient-to-r from-gray-500/20 to-gray-600/20',
      border: 'border-gray-500/50',
      pulse: '',
      dot: 'bg-gray-400'
    },
    pending: {
      bg: 'bg-gradient-to-r from-yellow-500/20 to-yellow-600/20',
      border: 'border-yellow-500/50',
      pulse: 'animate-pulse',
      dot: 'bg-yellow-400'
    }
  };

  const config = statusConfig[status];

  return (
    <div className={`rounded-xl border p-6 shadow-lg hover:shadow-xl transition-all duration-200 ${config.bg} ${config.border}`}>
      <div className="flex items-start space-x-3">
        {icon && (
          <div className="text-emerald-400 mt-1">
            {icon}
          </div>
        )}
        <div className="flex-1">
          <div className="flex items-center space-x-2 mb-2">
            <h3 className="text-emerald-400 font-bold text-lg">{title}</h3>
            <div className={`w-2 h-2 rounded-full ${config.dot} ${config.pulse}`}></div>
          </div>
          <p className="text-gray-300">{description}</p>
        </div>
      </div>
    </div>
  );
};

export default StatusCard;
