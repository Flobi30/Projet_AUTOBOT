import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { useDomain } from '../contexts/DomainContext'

interface CapitalData {
  initial_capital: number
  current_capital: number
  profit: number
  roi: number
  trading_allocation: number
  ecommerce_allocation: number
  transactions: Array<{
    date: string
    type: string
    amount: number
    source: string
    status: string
  }>
}

const Capital: React.FC = () => {
  const [capitalData, setCapitalData] = useState<CapitalData | null>(null)
  const [loading, setLoading] = useState(true)
  const { isPublicDomain } = useDomain()

  useEffect(() => {
    const fetchCapitalData = async () => {
      try {
        const response = await axios.get('/api/capital/data')
        setCapitalData(response.data)
      } catch (error) {
        console.error('Error fetching capital data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchCapitalData()
  }, [])

  const handleDeposit = async () => {
    try {
      const response = await axios.post('/api/stripe/create-checkout-session', {
        amount: 5000,
        currency: 'eur'
      })
      
      if (response.data.url) {
        window.location.href = response.data.url
      }
    } catch (error) {
      console.error('Error creating checkout session:', error)
    }
  }

  if (loading) {
    return <div>Chargement des données de capital...</div>
  }

  return (
    <div className="dashboard-grid">
      <div className="card" style={{ gridColumn: 'span 12' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 className="neon-text">
            {isPublicDomain ? 'AUTOBOT Capital Deposit' : 'Gestion du Capital'}
          </h3>
          {isPublicDomain && (
            <button className="btn btn-primary" onClick={handleDeposit}>
              Effectuer un Dépôt
            </button>
          )}
        </div>
      </div>
      
      {capitalData && (
        <>
          <div className="metric-card">
            <div className="metric-title">Capital Initial</div>
            <div className="metric-value">€{capitalData.initial_capital}</div>
          </div>
          
          <div className="metric-card">
            <div className="metric-title">Capital Actuel</div>
            <div className="metric-value">€{capitalData.current_capital}</div>
          </div>
          
          <div className="metric-card">
            <div className="metric-title">Profit</div>
            <div className="metric-value" style={{ 
              color: capitalData.profit >= 0 ? 'var(--success-color)' : 'var(--danger-color)' 
            }}>
              €{capitalData.profit}
            </div>
          </div>
          
          <div className="metric-card">
            <div className="metric-title">ROI</div>
            <div className="metric-value" style={{ 
              color: capitalData.roi >= 0 ? 'var(--success-color)' : 'var(--danger-color)' 
            }}>
              {capitalData.roi}%
            </div>
          </div>
          
          {!isPublicDomain && (
            <>
              <div className="card" style={{ gridColumn: 'span 6' }}>
                <h4>Allocation du Capital</h4>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '20px' }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ color: 'var(--primary-color)', fontSize: '24px', fontWeight: 'bold' }}>
                      {capitalData.trading_allocation}%
                    </div>
                    <div>Trading</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ color: 'var(--info-color)', fontSize: '24px', fontWeight: 'bold' }}>
                      {capitalData.ecommerce_allocation}%
                    </div>
                    <div>E-commerce</div>
                  </div>
                </div>
              </div>
              
              <div className="card" style={{ gridColumn: 'span 6' }}>
                <h4>Actions</h4>
                <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
                  <button className="btn btn-primary" onClick={handleDeposit}>
                    Effectuer un Dépôt
                  </button>
                  <button className="btn btn-primary">
                    Demander un Retrait
                  </button>
                </div>
              </div>
            </>
          )}
          
          <div className="card" style={{ gridColumn: 'span 12' }}>
            <h4>Historique des Transactions</h4>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th>Montant</th>
                  <th>Source</th>
                  <th>Statut</th>
                </tr>
              </thead>
              <tbody>
                {capitalData.transactions.map((transaction, index) => (
                  <tr key={index}>
                    <td>{transaction.date}</td>
                    <td>{transaction.type}</td>
                    <td>€{transaction.amount}</td>
                    <td>{transaction.source}</td>
                    <td>
                      <span style={{ 
                        color: transaction.status === 'Completed' ? 'var(--success-color)' : 'var(--warning-color)' 
                      }}>
                        {transaction.status}
                      </span>
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

export default Capital
