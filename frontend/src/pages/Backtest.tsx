import React, { useState, useEffect } from 'react'
import axios from 'axios'

interface BacktestData {
  performance: number
  sharpe_ratio: number
  max_drawdown: number
  total_trades: number
  win_rate: number
  strategies: Array<{
    name: string
    status: string
    performance: number
  }>
}

const Backtest: React.FC = () => {
  const [backtestData, setBacktestData] = useState<BacktestData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchBacktestData = async () => {
      try {
        const response = await axios.get('/api/backtest/current')
        setBacktestData(response.data)
      } catch (error) {
        console.error('Error fetching backtest data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchBacktestData()
    const interval = setInterval(fetchBacktestData, 30000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return <div>Chargement des données de backtest...</div>
  }

  return (
    <div className="dashboard-grid">
      <div className="card" style={{ gridColumn: 'span 12' }}>
        <h3 className="neon-text">Backtest AUTOBOT</h3>
        <p>Résultats des tests de stratégies en temps réel.</p>
      </div>
      
      {backtestData && (
        <>
          <div className="metric-card">
            <div className="metric-title">Performance</div>
            <div className="metric-value" style={{ 
              color: backtestData.performance >= 0 ? 'var(--success-color)' : 'var(--danger-color)' 
            }}>
              {backtestData.performance.toFixed(2)}%
            </div>
          </div>
          
          <div className="metric-card">
            <div className="metric-title">Ratio de Sharpe</div>
            <div className="metric-value">{backtestData.sharpe_ratio.toFixed(2)}</div>
          </div>
          
          <div className="metric-card">
            <div className="metric-title">Taux de Réussite</div>
            <div className="metric-value">{backtestData.win_rate.toFixed(0)}%</div>
          </div>
          
          <div className="card" style={{ gridColumn: 'span 12' }}>
            <h4>Stratégies Testées</h4>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Stratégie</th>
                  <th>Statut</th>
                  <th>Performance</th>
                </tr>
              </thead>
              <tbody>
                {backtestData.strategies.map((strategy, index) => (
                  <tr key={index}>
                    <td>{strategy.name}</td>
                    <td>
                      <span style={{ 
                        color: strategy.status === 'Active' ? 'var(--success-color)' : 'var(--warning-color)' 
                      }}>
                        {strategy.status}
                      </span>
                    </td>
                    <td style={{ 
                      color: strategy.performance >= 0 ? 'var(--success-color)' : 'var(--danger-color)' 
                    }}>
                      {strategy.performance.toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default Backtest
