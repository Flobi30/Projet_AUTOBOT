import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  Server, 
  Database, 
  Wifi, 
  Cpu, 
  HardDrive, 
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Terminal
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

interface HealthMetric {
  name: string;
  value: number;
  max: number;
  unit: string;
  status: 'healthy' | 'warning' | 'critical';
}

interface SystemStatus {
  overall: 'healthy' | 'warning' | 'critical';
  timestamp: string;
  metrics: {
    ram: HealthMetric;
    cpu: HealthMetric;
    disk: HealthMetric;
    docker: { running: boolean; containers: string[] };
    kraken: { accessible: boolean; latency: number };
    database: { exists: boolean; size_mb: number };
  };
  issues: string[];
  recommendations: string[];
}

// Données simulées pour démonstration
const mockStatus: SystemStatus = {
  overall: 'healthy',
  timestamp: new Date().toISOString(),
  metrics: {
    ram: { name: 'RAM', value: 45, max: 100, unit: '%', status: 'healthy' },
    cpu: { name: 'CPU', value: 23, max: 100, unit: '%', status: 'healthy' },
    disk: { name: 'Disque', value: 32, max: 100, unit: '%', status: 'healthy' },
    docker: { running: true, containers: ['autobot-v2', 'redis'] },
    kraken: { accessible: true, latency: 145 },
    database: { exists: true, size_mb: 12.5 }
  },
  issues: [],
  recommendations: ['Aucune action requise, le système fonctionne bien !']
};

// Historique simulé pour le graphique
const generateHistory = () => {
  const data = [];
  for (let i = 24; i >= 0; i--) {
    data.push({
      time: `${i}h`,
      ram: 40 + Math.random() * 20,
      cpu: 20 + Math.random() * 15,
      latency: 100 + Math.random() * 100
    });
  }
  return data;
};

const StatusBadge: React.FC<{ status: 'healthy' | 'warning' | 'critical' }> = ({ status }) => {
  const colors = {
    healthy: 'bg-green-500/20 text-green-400 border-green-500/30',
    warning: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    critical: 'bg-red-500/20 text-red-400 border-red-500/30'
  };
  
  const labels = {
    healthy: 'OK',
    warning: 'Attention',
    critical: 'Critique'
  };
  
  const icons = {
    healthy: <CheckCircle className="w-4 h-4" />,
    warning: <AlertTriangle className="w-4 h-4" />,
    critical: <XCircle className="w-4 h-4" />
  };

  return (
    <span className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border ${colors[status]}`}>
      {icons[status]}
      {labels[status]}
    </span>
  );
};

const MetricCard: React.FC<{ 
  icon: React.ReactNode; 
  title: string; 
  metric: HealthMetric;
  subtext?: string;
}> = ({ icon, title, metric, subtext }) => {
  const percentage = (metric.value / metric.max) * 100;
  const barColors = {
    healthy: 'bg-green-500',
    warning: 'bg-yellow-500',
    critical: 'bg-red-500'
  };

  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-5">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gray-700/50 rounded-lg">
            {icon}
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-400">{title}</h3>
            <p className="text-2xl font-bold text-white">
              {metric.value}{metric.unit}
            </p>
          </div>
        </div>
        <StatusBadge status={metric.status} />
      </div>
      
      <div className="space-y-2">
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
          <div 
            className={`h-full ${barColors[metric.status]} transition-all duration-500`}
            style={{ width: `${percentage}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-gray-500">
          <span>0{metric.unit}</span>
          <span>{metric.max}{metric.unit}</span>
        </div>
      </div>
      
      {subtext && (
        <p className="mt-3 text-sm text-gray-500">{subtext}</p>
      )}
    </div>
  );
};

const ServiceCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  status: 'up' | 'down' | 'warning';
  details: string[];
}> = ({ icon, title, status, details }) => {
  const statusColors = {
    up: 'text-green-400',
    down: 'text-red-400',
    warning: 'text-yellow-400'
  };

  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-5">
      <div className="flex items-center gap-3 mb-4">
        <div className={`p-2 bg-gray-700/50 rounded-lg ${statusColors[status]}`}>
          {icon}
        </div>
        <div>
          <h3 className="font-medium text-white">{title}</h3>
          <span className={`text-sm ${statusColors[status]}`}>
            {status === 'up' ? 'En ligne' : status === 'down' ? 'Hors ligne' : 'Dégradé'}
          </span>
        </div>
      </div>
      <ul className="space-y-1.5">
        {details.map((detail, i) => (
          <li key={i} className="text-sm text-gray-400 flex items-center gap-2">
            <span className="w-1.5 h-1.5 bg-gray-500 rounded-full" />
            {detail}
          </li>
        ))}
      </ul>
    </div>
  );
};

const IssuesPanel: React.FC<{ issues: string[]; recommendations: string[] }> = ({ 
  issues, 
  recommendations 
}) => {
  if (issues.length === 0) {
    return (
      <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-5">
        <div className="flex items-center gap-3 text-green-400">
          <CheckCircle className="w-6 h-6" />
          <div>
            <h3 className="font-semibold">Tout fonctionne parfaitement</h3>
            <p className="text-sm text-green-400/70">Aucun problème détecté</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {issues.length > 0 && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-5">
          <h3 className="flex items-center gap-2 font-semibold text-red-400 mb-3">
            <AlertTriangle className="w-5 h-5" />
            Problèmes détectés ({issues.length})
          </h3>
          <ul className="space-y-2">
            {issues.map((issue, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-red-300">
                <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {issue}
              </li>
            ))}
          </ul>
        </div>
      )}
      
      <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-5">
        <h3 className="flex items-center gap-2 font-semibold text-blue-400 mb-3">
          <Terminal className="w-5 h-5" />
          Recommandations
        </h3>
        <ul className="space-y-2">
          {recommendations.map((rec, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-blue-300">
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full mt-2 flex-shrink-0" />
              {rec}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

const Diagnostic: React.FC = () => {
  const [status, setStatus] = useState<SystemStatus>(mockStatus);
  const [loading, setLoading] = useState(false);
  const [history] = useState(generateHistory());

  const refreshStatus = () => {
    setLoading(true);
    // Simuler un appel API
    setTimeout(() => {
      setStatus({
        ...mockStatus,
        timestamp: new Date().toISOString(),
        metrics: {
          ...mockStatus.metrics,
          ram: { 
            ...mockStatus.metrics.ram, 
            value: Math.floor(35 + Math.random() * 30) 
          },
          cpu: { 
            ...mockStatus.metrics.cpu, 
            value: Math.floor(15 + Math.random() * 25) 
          }
        }
      });
      setLoading(false);
    }, 1000);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Diagnostic Système</h1>
          <p className="text-gray-400">
            Dernière mise à jour: {new Date(status.timestamp).toLocaleString('fr-FR')}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <StatusBadge status={status.overall} />
          <button
            onClick={refreshStatus}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 
                       disabled:opacity-50 disabled:cursor-not-allowed rounded-lg 
                       text-white font-medium transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Actualiser
          </button>
        </div>
      </div>

      {/* Métriques principales */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <MetricCard 
          icon={<Cpu className="w-5 h-5 text-blue-400" />}
          title="Utilisation RAM"
          metric={status.metrics.ram}
          subtext="4 GB total sur CAX11"
        />
        <MetricCard 
          icon={<Activity className="w-5 h-5 text-purple-400" />}
          title="Utilisation CPU"
          metric={status.metrics.cpu}
          subtext="2 vCPU ARM64"
        />
        <MetricCard 
          icon={<HardDrive className="w-5 h-5 text-orange-400" />}
          title="Espace Disque"
          metric={status.metrics.disk}
          subtext="40 GB SSD + 10 GB volume"
        />
      </div>

      {/* Services */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <ServiceCard
          icon={<Server className="w-5 h-5" />}
          title="Docker"
          status={status.metrics.docker.running ? 'up' : 'down'}
          details={[
            `Conteneurs: ${status.metrics.docker.containers.length} actifs`,
            'autobot-v2: En cours',
            'Réseau: Connecté'
          ]}
        />
        <ServiceCard
          icon={<Wifi className="w-5 h-5" />}
          title="Kraken API"
          status={status.metrics.kraken.accessible ? 'up' : 'down'}
          details={[
            `Latence: ${status.metrics.kraken.latency}ms`,
            'Connexion: HTTPS',
            'Sandbox: Actif'
          ]}
        />
        <ServiceCard
          icon={<Database className="w-5 h-5" />}
          title="Base de données"
          status={status.metrics.database.exists ? 'up' : 'down'}
          details={[
            `Taille: ${status.metrics.database.size_mb} MB`,
            'Type: SQLite',
            'Backups: Quotidiens'
          ]}
        />
      </div>

      {/* Graphique d'historique */}
      <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6 mb-8">
        <h3 className="text-lg font-semibold text-white mb-4">Historique des 24 dernières heures</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history}>
              <XAxis dataKey="time" stroke="#6b7280" />
              <YAxis stroke="#6b7280" />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1f2937', 
                  border: '1px solid #374151',
                  borderRadius: '8px'
                }}
              />
              <Line type="monotone" dataKey="ram" stroke="#3b82f6" name="RAM %" strokeWidth={2} />
              <Line type="monotone" dataKey="cpu" stroke="#a855f7" name="CPU %" strokeWidth={2} />
              <Line type="monotone" dataKey="latency" stroke="#f97316" name="Latence ms" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Problèmes et recommandations */}
      <IssuesPanel issues={status.issues} recommendations={status.recommendations} />

      {/* Actions rapides */}
      <div className="mt-8 bg-gray-800/30 border border-gray-700 rounded-xl p-6">
        <h3 className="text-lg font-semibold text-white mb-4">Actions rapides</h3>
        <div className="flex flex-wrap gap-3">
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-white transition-colors">
            Voir les logs complets
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-white transition-colors">
            Redémarrer le bot
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-white transition-colors">
            Backup manuel
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-white transition-colors">
            Nettoyer les logs
          </button>
        </div>
      </div>
    </div>
  );
};

export default Diagnostic;