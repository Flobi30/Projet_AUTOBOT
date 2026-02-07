import React, { useState } from 'react';
import { Save, Shield, Bell, Database, Zap, AlertTriangle } from 'lucide-react';

const Settings: React.FC = () => {
  const [settings, setSettings] = useState({
    // Trading Settings
    maxRisk: '2',
    stopLoss: '5',
    takeProfit: '10',
    tradingMode: 'conservative',
    
    // Notification Settings
    emailNotifications: true,
    pushNotifications: true,
    tradeAlerts: true,
    performanceReports: false,
    
    // Security Settings
    twoFactorAuth: false,
    apiKeyRotation: true,
    
    // System Settings
    autoBackup: true,
    dataRetention: '1year',
  });

  const handleSettingChange = (key: string, value: any) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    console.log('Saving settings:', settings);
    // Ici vous ajouterez la logique pour sauvegarder les paramètres
  };

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-emerald-400 mb-2">Paramètres</h1>
        <p className="text-gray-400">Configuration du système AUTOBOT</p>
      </div>

      <div className="space-y-6">
        {/* Trading Configuration */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <div className="flex items-center space-x-3 mb-4">
            <Zap className="w-6 h-6 text-emerald-400" />
            <h2 className="text-xl font-semibold text-emerald-400">Configuration Trading</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-gray-400 text-sm mb-2">Risque Maximum par Trade (%)</label>
              <input
                type="number"
                value={settings.maxRisk}
                onChange={(e) => handleSettingChange('maxRisk', e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500"
                min="0.1"
                max="10"
                step="0.1"
              />
            </div>

            <div>
              <label className="block text-gray-400 text-sm mb-2">Stop Loss par Défaut (%)</label>
              <input
                type="number"
                value={settings.stopLoss}
                onChange={(e) => handleSettingChange('stopLoss', e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500"
                min="1"
                max="20"
              />
            </div>

            <div>
              <label className="block text-gray-400 text-sm mb-2">Take Profit par Défaut (%)</label>
              <input
                type="number"
                value={settings.takeProfit}
                onChange={(e) => handleSettingChange('takeProfit', e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500"
                min="1"
                max="50"
              />
            </div>

            <div>
              <label className="block text-gray-400 text-sm mb-2">Mode de Trading</label>
              <select
                value={settings.tradingMode}
                onChange={(e) => handleSettingChange('tradingMode', e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500"
              >
                <option value="conservative">Conservateur</option>
                <option value="moderate">Modéré</option>
                <option value="aggressive">Agressif</option>
              </select>
            </div>
          </div>
        </div>

        {/* Notifications */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <div className="flex items-center space-x-3 mb-4">
            <Bell className="w-6 h-6 text-emerald-400" />
            <h2 className="text-xl font-semibold text-emerald-400">Notifications</h2>
          </div>

          <div className="space-y-4">
            {[
              { key: 'emailNotifications', label: 'Notifications Email', description: 'Recevoir les alertes par email' },
              { key: 'pushNotifications', label: 'Notifications Push', description: 'Notifications en temps réel' },
              { key: 'tradeAlerts', label: 'Alertes de Trading', description: 'Notifications pour chaque trade' },
              { key: 'performanceReports', label: 'Rapports de Performance', description: 'Rapports hebdomadaires automatiques' },
            ].map((item) => (
              <div key={item.key} className="flex justify-between items-center p-3 bg-gray-700 rounded-lg">
                <div>
                  <h4 className="text-white font-medium">{item.label}</h4>
                  <p className="text-gray-400 text-sm">{item.description}</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settings[item.key as keyof typeof settings] as boolean}
                    onChange={(e) => handleSettingChange(item.key, e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
                </label>
              </div>
            ))}
          </div>
        </div>

        {/* Security */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <div className="flex items-center space-x-3 mb-4">
            <Shield className="w-6 h-6 text-emerald-400" />
            <h2 className="text-xl font-semibold text-emerald-400">Sécurité</h2>
          </div>

          <div className="space-y-4">
            <div className="flex justify-between items-center p-3 bg-gray-700 rounded-lg">
              <div>
                <h4 className="text-white font-medium">Authentification à 2 Facteurs</h4>
                <p className="text-gray-400 text-sm">Sécurité renforcée pour votre compte</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.twoFactorAuth}
                  onChange={(e) => handleSettingChange('twoFactorAuth', e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
              </label>
            </div>

            <div className="flex justify-between items-center p-3 bg-gray-700 rounded-lg">
              <div>
                <h4 className="text-white font-medium">Rotation Automatique des Clés API</h4>
                <p className="text-gray-400 text-sm">Renouvellement automatique mensuel</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.apiKeyRotation}
                  onChange={(e) => handleSettingChange('apiKeyRotation', e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
              </label>
            </div>
          </div>
        </div>

        {/* System Settings */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <div className="flex items-center space-x-3 mb-4">
            <Database className="w-6 h-6 text-emerald-400" />
            <h2 className="text-xl font-semibold text-emerald-400">Système</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="flex justify-between items-center p-3 bg-gray-700 rounded-lg">
              <div>
                <h4 className="text-white font-medium">Sauvegarde Automatique</h4>
                <p className="text-gray-400 text-sm">Backup quotidien des données</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.autoBackup}
                  onChange={(e) => handleSettingChange('autoBackup', e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
              </label>
            </div>

            <div>
              <label className="block text-gray-400 text-sm mb-2">Rétention des Données</label>
              <select
                value={settings.dataRetention}
                onChange={(e) => handleSettingChange('dataRetention', e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500"
              >
                <option value="6months">6 mois</option>
                <option value="1year">1 an</option>
                <option value="2years">2 ans</option>
                <option value="forever">Illimité</option>
              </select>
            </div>
          </div>
        </div>

        {/* Danger Zone */}
        <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-6">
          <div className="flex items-center space-x-3 mb-4">
            <AlertTriangle className="w-6 h-6 text-red-400" />
            <h2 className="text-xl font-semibold text-red-400">Zone de Danger</h2>
          </div>

          <div className="space-y-4">
            <button className="bg-red-500/20 hover:bg-red-500/30 border border-red-500/50 text-red-400 px-4 py-2 rounded-lg transition-colors">
              Réinitialiser les Paramètres
            </button>
            <button className="bg-red-500/20 hover:bg-red-500/30 border border-red-500/50 text-red-400 px-4 py-2 rounded-lg transition-colors ml-3">
              Arrêter le Trading Bot
            </button>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end">
          <button
            onClick={handleSave}
            className="bg-emerald-500 hover:bg-emerald-600 text-white px-6 py-3 rounded-lg flex items-center space-x-2 transition-colors"
          >
            <Save className="w-5 h-5" />
            <span>Sauvegarder les Paramètres</span>
          </button>
        </div>
      </div>
    </div>
  );
};

export default Settings;
