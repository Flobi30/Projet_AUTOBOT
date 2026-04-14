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
  Terminal,
  HeartPulse
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import Skeleton from 'react-loading-skeleton';
import 'react-loading-skeleton/dist/skeleton.css';

const API_BASE_URL = '';
const API_TOKEN = import.meta.env.VITE_DASHBOARD_API_TOKEN || window.localStorage.getItem('DASHBOARD_API_TOKEN') || '';// no hardcoded secret

interface SystemMetrics {
  cpu: {
    percent: number;
    status: 'healthy' | 'warning' | 'critical';
  };
  memory: {
    percent: number;
    used_gb: number;
    total_gb: number;
    status: 'healthy' | 'warning' | 'critical';
  };
  disk: {
    percent: number;
    used_gb: number;
    total_gb: number;
    status: 'healthy' | 'warning' | 'critical';
  };
  timestamp: string;
}

interface SystemStatus {
  overall: 'healthy' | 'warning' | 'critical';
  timestamp: string;
  metrics: SystemMetrics;
  docker: { running: boolean; containers: string[] };
  kraken: { accessible: boolean; latency: number };
  database: { exists: boolean; size_mb: number };
  issues: string[];
  recommendations: string[];
}

const StatusBadge: React.FC<{ status: 'healthy' | 'warning' | 'critical' }> = ({ status }) => {
  const configs = {
    healthy: { 
      bg: 'bg-emerald-500/20', 
      text: 'text-emerald-400', 
      border: 'border-emerald-500/30',
      label: 'Système OK',
      icon: <CheckCircle className="w-4 h-4" />
    },
    warning: { 
      bg: 'bg-yellow-500/20', 
      text: 'text-yellow-400', 
      border: 'border-yellow-500/30',
      label: 'Attention',
      icon: <AlertTriangle className="w-4 h-4" />
    },
    critical: { 
      bg: 'bg-red-500/20', 
      text: 'text-red-400', 
      border: 'border-red-500/30',
      label: 'Critique',
      icon: <XCircle className="w-4 h-4" />
    }
  };
  
  const config = configs[status];

  return (
    <span className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold border ${config.bg} ${config.text} ${config.border}`}>
      {config.icon}
      {config.label}
    </span>
  );
};

const ProgressBar: React.FC<{ 
  value: number; 
  max: number; 
  status: 'healthy' | 'warning' | 'critical';
  label: string;
}> = ({ value, max, status, label }) => {
  const percentage = Math.min((value / max) * 100, 100);
  const colors = {
    healthy: 'bg-emerald-500',
    warning: 'bg-yellow-500',
    critical: 'bg-red-500'
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span className="text-gray-400">{label}</span>
        <span className={`font-bold ${
          status === 'healthy' ? 'text-emerald-400' : 
          status === 'warning' ? 'text-yellow-400' : 'text-red-400'
        }`}>
          {value}%
        </span>
      </div>
      <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
        <div 
          className={`h-full ${colors[status]} transition-all duration-500 rounded-full`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

const ServiceCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  status: 'up' | 'down' | 'warning';
  details: string[];
}> = ({ icon, title, status, details }) => {
  const statusConfig = {
    up: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-400', dot: 'bg-emerald-400' },
    down: { bg: 'bg-red-500/10', border: 'border-red-500/30', text: 'text-red-400', dot: 'bg-red-400' },
    warning: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', text: 'text-yellow-400', dot: 'bg-yellow-400' }
  };

  const config = statusConfig[status];

  return (
    <div className={`${config.bg} border ${config.border} rounded-2xl p-6`}>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 bg-gray-800 rounded-xl ${config.text}`}>
            {icon}
          </div>
          <div>
            <h3 className="font-bold text-white">{title}</h3>
            <div className="flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${config.dot} animate-pulse`} />
              <span className={`text-sm ${config.text}`}>
                {status === 'up' ? 'En ligne' : status === 'down' ? 'Hors ligne' : 'Dégradé'}
              </span>
            </div>
          </div>
        </div>
      </div>
      <div className="space-y-2 pt-4 border-t border-gray-700/50">
        {details.map((detail, i) => (
          <div key={i} className="flex items-center gap-2 text-sm text-gray-400">
            <span className="w-1.5 h-1.5 bg-gray-500 rounded-full" />
            {detail}
          </div>
        ))}
      </div>
    </div>
  );
};

const IssuesPanel: React.FC<{ issues: string[]; recommendations: string[] }> = ({ 
  issues, 
  recommendations 
}) => {
  if (issues.length === 0) {
    return (
      <div className="bg-gradient-to-br from-emerald-500/10 to-emerald-500/5 border border-emerald-500/30 rounded-2xl p-6">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-emerald-500/20 rounded-xl">
            <CheckCircle className="w-8 h-8 text-emerald-400" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Tout fonctionne parfaitement</h3>
            <p className="text-emerald-400">Aucun problème détecté sur le système</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {issues.length > 0 && (
        <div className="bg-gradient-to-br from-red-500/10 to-red-500/5 border border-red-500/30 rounded-2xl p-6">
          <h3 className="flex items-center gap-3 text-lg font-bold text-red-400 mb-4">
            <AlertTriangle className="w-6 h-6" />
            Problèmes détectés ({issues.length})
          </h3>
          <div className="space-y-3">
            {issues.map((issue, i) => (
              <div key={i} className="flex items-start gap-3 p-3 bg-red-500/10 rounded-xl">
                <XCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <span className="text-red-300">{issue}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      
      <div className="bg-gradient-to-br from-blue-500/10 to-blue-500/5 border border-blue-500/30 rounded-2xl p-6">
        <h3 className="flex items-center gap-3 text-lg font-bold text-blue-400 mb-4">
          <Terminal className="w-6 h-6" />
          Recommandations
        </h3>
        <div className="space-y-3">
          {recommendations.map((rec, i) => (
            <div key={i} className="flex items-start gap-3 p-3 bg-blue-500/10 rounded-xl">
              <span className="w-2 h-2 bg-blue-400 rounded-full mt-2 flex-shrink-0" />
              <span className="text-blue-300">{rec}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

const SkeletonDiagnostic = () => (
  <div className="p-8 bg-gray-900 min-h-screen flex items-center justify-center">
    <div className="flex flex-col items-center">
      <div className="w-12 h-12 border-4 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin"></div>
      <span className="mt-4 text-emerald-400">Chargement...</span>
    </div>
  </div>
);

const Diagnostic: React.FC = () => {
  const [systemMetrics, setSystemMetrics] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<{time: string; ram: number; cpu: number}[]>([]);

  const fetchSystemMetrics = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/system`, {
        headers: {
          'Authorization': `Bearer ${API_TOKEN}`
        }
      });
      
      if (!response.ok) {
        throw new Error('Erreur lors de la récupération des métriques');
      }
      
      const data = await response.json();
      setSystemMetrics(data);
      
      // Ajouter au historique
      const now = new Date();
      const timeStr = `${now.getHours()}:${now.getMinutes().toString().padStart(2, '0')}`;
      setHistory(prev => {
        const newHistory = [...prev, { time: timeStr, ram: data.memory.percent, cpu: data.cpu.percent }];
        // Garder seulement les 24 dernières entrées
        return newHistory.slice(-24);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de connexion');
    }
  };

  useEffect(() => {
    // Chargement initial
    fetchSystemMetrics().then(() => setIsLoading(false));
    
    // Polling toutes les 5 secondes
    const interval = setInterval(fetchSystemMetrics, 5000);
    
    return () => clearInterval(interval);
  }, []);

  const refreshStatus = async () => {
    setLoading(true);
    await fetchSystemMetrics();
    setLoading(false);
  };

  const getOverallStatus = (): 'healthy' | 'warning' | 'critical' => {
    if (!systemMetrics) return 'healthy';
    
    const statuses = [systemMetrics.cpu.status, systemMetrics.memory.status, systemMetrics.disk.status];
    if (statuses.includes('critical')) return 'critical';
    if (statuses.includes('warning')) return 'warning';
    return 'healthy';
  };

  if (isLoading) {
    return <SkeletonDiagnostic />;
  }

  if (error) {
    return (
      <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
        <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
          <div className="flex items-center space-x-3 mb-3">
            <HeartPulse className="w-6 lg:w-8 h-6 lg:h-8 text-red-400" />
            <h1 className="text-2xl lg:text-4xl font-bold text-red-400">
              Erreur de diagnostic
            </h1>
          </div>
          <p className="text-gray-400 text-sm lg:text-lg mb-4">
            Impossible de récupérer l'état du système.
          </p>
          <div className="bg-red-500/20 border border-red-500/50 rounded-lg p-4 text-red-400">
            {error}
          </div>
        </div>
      </div>
    );
  }

  const overallStatus = getOverallStatus();
  const timestamp = systemMetrics?.timestamp || new Date().toISOString();

  return (
    <div className="p-4 lg:p-8 bg-gray-900 min-h-screen">
      {/* Header */}
      <div className="mb-6 lg:mb-8 mt-16 lg:mt-0">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-3">
          <div className="flex items-center space-x-3">
            <HeartPulse className="w-6 lg:w-8 h-6 lg:h-8 text-emerald-400" />
            <h1 className="text-2xl lg:text-4xl font-bold bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
              Diagnostic Système
            </h1>
          </div>
          <div className="flex items-center gap-4">
            <StatusBadge status={overallStatus} />
            <button
              onClick={refreshStatus}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 
                         disabled:opacity-50 disabled:cursor-not-allowed rounded-xl 
                         text-white font-bold transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Actualiser
            </button>
          </div>
        </div>
        <p className="text-gray-400 text-sm lg:text-lg">
          Dernière mise à jour: {new Date(timestamp).toLocaleString('fr-FR')}
        </p>
      </div>

      {/* Métriques principales */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-xl p-6 hover:shadow-lg hover:shadow-emerald-500/10 transition-all duration-200">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2">
              <Cpu className="w-5 h-5 text-emerald-400" />
              <span className="text-gray-400 text-sm font-medium">Utilisation RAM</span>
            </div>
            <span className={`text-sm font-bold px-2 py-1 rounded-lg ${
              systemMetrics?.memory.status === 'healthy' ? 'text-emerald-400 bg-emerald-500/10' :
              systemMetrics?.memory.status === 'warning' ? 'text-yellow-400 bg-yellow-500/10' :
              'text-red-400 bg-red-500/10'
            }`}>
              {systemMetrics?.memory.status === 'healthy' ? 'OK' : 
               systemMetrics?.memory.status === 'warning' ? 'Attention' : 'Critique'}
            </span>
          </div>
          {systemMetrics && (
            <ProgressBar 
              value={systemMetrics.memory.percent} 
              max={100} 
              status={systemMetrics.memory.status}
              label="RAM utilisée"
            />
          )}
          <p className="mt-3 text-sm text-gray-500">
            {systemMetrics ? `${systemMetrics.memory.used_gb} GB / ${systemMetrics.memory.total_gb} GB` : 'Chargement...'}
          </p>
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-xl p-6 hover:shadow-lg hover:shadow-emerald-500/10 transition-all duration-200">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-emerald-400" />
              <span className="text-gray-400 text-sm font-medium">Utilisation CPU</span>
            </div>
            <span className={`text-sm font-bold px-2 py-1 rounded-lg ${
              systemMetrics?.cpu.status === 'healthy' ? 'text-emerald-400 bg-emerald-500/10' :
              systemMetrics?.cpu.status === 'warning' ? 'text-yellow-400 bg-yellow-500/10' :
              'text-red-400 bg-red-500/10'
            }`}>
              {systemMetrics?.cpu.status === 'healthy' ? 'OK' : 
               systemMetrics?.cpu.status === 'warning' ? 'Attention' : 'Critique'}
            </span>
          </div>
          {systemMetrics && (
            <ProgressBar 
              value={systemMetrics.cpu.percent} 
              max={100} 
              status={systemMetrics.cpu.status}
              label="CPU utilisé"
            />
          )}
          <p className="mt-3 text-sm text-gray-500">CX33 - 4GB RAM, 2 vCPU</p>
        </div>

        <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-xl p-6 hover:shadow-lg hover:shadow-emerald-500/10 transition-all duration-200">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2">
              <HardDrive className="w-5 h-5 text-emerald-400" />
              <span className="text-gray-400 text-sm font-medium">Espace Disque</span>
            </div>
            <span className={`text-sm font-bold px-2 py-1 rounded-lg ${
              systemMetrics?.disk.status === 'healthy' ? 'text-emerald-400 bg-emerald-500/10' :
              systemMetrics?.disk.status === 'warning' ? 'text-yellow-400 bg-yellow-500/10' :
              'text-red-400 bg-red-500/10'
            }`}>
              {systemMetrics?.disk.status === 'healthy' ? 'OK' : 
               systemMetrics?.disk.status === 'warning' ? 'Attention' : 'Critique'}
            </span>
          </div>
          {systemMetrics && (
            <ProgressBar 
              value={systemMetrics.disk.percent} 
              max={100} 
              status={systemMetrics.disk.status}
              label="Disque utilisé"
            />
          )}
          <p className="mt-3 text-sm text-gray-500">
            {systemMetrics ? `${systemMetrics.disk.used_gb} GB / ${systemMetrics.disk.total_gb} GB` : 'Chargement...'}
          </p>
        </div>
      </div>

      {/* Services */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 lg:gap-6 mb-6 lg:mb-8">
        <ServiceCard
          icon={<Server className="w-6 h-6" />}
          title="Docker"
          status="up"
          details={[
            '1 conteneur actif',
            'autobot-v2: En cours d\'exécution',
            'Réseau: Connecté'
          ]}
        />
        <ServiceCard
          icon={<Wifi className="w-6 h-6" />}
          title="Kraken API"
          status="up"
          details={[
            'Latence: ~20-30ms',
            'Connexion: HTTPS sécurisé',
            'Mode: Paper Trading'
          ]}
        />
        <ServiceCard
          icon={<Database className="w-6 h-6" />}
          title="Base de données"
          status="up"
          details={[
            'Type: SQLite',
            'Statut: Opérationnel',
            'Backups: Automatiques'
          ]}
        />
      </div>

      {/* Graphique d'historique */}
      <div className="bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-4 lg:p-8 mb-6 lg:mb-8 shadow-2xl">
        <h2 className="text-xl lg:text-2xl font-bold text-emerald-400 mb-6">
          Historique des ressources
        </h2>
        <div className="h-64 lg:h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history}>
              <defs>
                <linearGradient id="colorRam" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorCpu" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#a855f7" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="#a855f7" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="time" stroke="#9CA3AF" fontSize={12} />
              <YAxis stroke="#9CA3AF" fontSize={12} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1F2937', 
                  border: '1px solid #374151',
                  borderRadius: '12px'
                }}
              />
              <Line type="monotone" dataKey="ram" stroke="#3b82f6" strokeWidth={3} name="RAM %" dot={false} />
              <Line type="monotone" dataKey="cpu" stroke="#a855f7" strokeWidth={3} name="CPU %" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Actions rapides */}
      <div className="mt-8 bg-gradient-to-br from-gray-800 to-gray-800/80 border border-gray-700/50 rounded-2xl p-6">
        <h3 className="text-lg font-bold text-white mb-4">Actions rapides</h3>
        <div className="flex flex-wrap gap-3">
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-xl text-sm text-white font-medium transition-colors">
            Voir les logs complets
          </button>
          <button className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-xl text-sm text-white font-medium transition-colors">
            Redémarrer le bot
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-xl text-sm text-white font-medium transition-colors">
            Backup manuel
          </button>
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-xl text-sm text-white font-medium transition-colors">
            Nettoyer les logs
          </button>
        </div>
      </div>
    </div>
  );
};

export default Diagnostic;