import React from 'react'

const Dashboard: React.FC = () => {
  return (
    <div className="dashboard-grid">
      <div className="card" style={{ gridColumn: 'span 12' }}>
        <h3 className="neon-text">Dashboard AUTOBOT</h3>
        <p>Bienvenue sur le tableau de bord AUTOBOT.</p>
      </div>
      
      <div className="metric-card">
        <div className="metric-title">Capital Total</div>
        <div className="metric-value">€1,000</div>
      </div>
      
      <div className="metric-card">
        <div className="metric-title">Profit</div>
        <div className="metric-value">€0</div>
      </div>
      
      <div className="metric-card">
        <div className="metric-title">ROI</div>
        <div className="metric-value">0%</div>
      </div>
    </div>
  )
}

export default Dashboard
