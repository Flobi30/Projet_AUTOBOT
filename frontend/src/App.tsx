import { useEffect, useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { DomainProvider } from './contexts/DomainContext'
import Layout from './components/Layout'
import Backtest from './pages/Backtest'
import Capital from './pages/Capital'
import Login from './pages/Login'
import PrivateRoute from './components/PrivateRoute'
import PublicRoute from './components/PublicRoute'

function PublicCapitalPage() {
  const [loading, setLoading] = useState(false)

  const createStripeSession = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/stripe/create-checkout-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: 5000, currency: 'eur' })
      })
      const data = await response.json()
      if (data.url) {
        window.location.href = data.url
      }
    } catch (error) {
      console.error('Erreur Stripe:', error)
      window.location.href = 'https://checkout.stripe.com/c/pay/cs_live_a1bwMvxbB6EdyzeuuW3CIw0xMzLJYoz25vlJc8HNjY1qxbze5B2fRMQGoz'
    }
    setLoading(false)
  }

  return (
    <div style={{
      fontFamily: 'Arial, sans-serif',
      background: '#0a0a0a',
      color: '#00ff88',
      margin: 0,
      padding: '20px',
      textAlign: 'center',
      minHeight: '100vh'
    }}>
      <div style={{
        maxWidth: '600px',
        margin: '50px auto',
        padding: '30px',
        border: '2px solid #00ff88',
        borderRadius: '10px',
        background: 'rgba(0, 255, 136, 0.1)'
      }}>
        <h1 style={{ color: '#00ff88', marginBottom: '30px' }}>🤖 AUTOBOT Capital</h1>
        <p style={{ margin: '20px 0', lineHeight: '1.6' }}>Plateforme de gestion de capital automatisée</p>
        <p style={{ margin: '20px 0', lineHeight: '1.6' }}>Effectuez vos dépôts et retraits en toute sécurité</p>
        
        <button
          onClick={createStripeSession}
          disabled={loading}
          style={{
            background: loading ? '#666' : '#00ff88',
            color: '#0a0a0a',
            padding: '15px 30px',
            border: 'none',
            borderRadius: '5px',
            fontSize: '18px',
            cursor: loading ? 'not-allowed' : 'pointer',
            margin: '10px',
            textDecoration: 'none',
            display: 'inline-block'
          }}
        >
          {loading ? '⏳ Chargement...' : '💳 Effectuer un Dépôt'}
        </button>
        
        <button
          onClick={() => alert('Fonctionnalité de retrait disponible prochainement')}
          style={{
            background: '#00ff88',
            color: '#0a0a0a',
            padding: '15px 30px',
            border: 'none',
            borderRadius: '5px',
            fontSize: '18px',
            cursor: 'pointer',
            margin: '10px',
            textDecoration: 'none',
            display: 'inline-block'
          }}
        >
          💰 Effectuer un Retrait
        </button>

        <div style={{ marginTop: '30px', fontSize: '14px', opacity: '0.8' }}>
          <p>🔒 Interface sécurisée pour les transactions AUTOBOT</p>
          <p>Pour accéder à l'interface complète, connectez-vous sur le serveur privé</p>
        </div>
      </div>
    </div>
  )
}

function App() {
  const [isPublicDomain, setIsPublicDomain] = useState(false)
  const [domainChecked, setDomainChecked] = useState(false)

  useEffect(() => {
    const hostname = window.location.hostname
    const isPublic = hostname.includes('stripe-autobot.fr')
    setIsPublicDomain(isPublic)
    setDomainChecked(true)
    
    console.log('Domain detection:', { hostname, isPublic })
  }, [])

  if (!domainChecked) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        background: '#0a0a0a',
        color: '#00ff88'
      }}>
        <div>🤖 Chargement AUTOBOT...</div>
      </div>
    )
  }

  if (isPublicDomain) {
    return <PublicCapitalPage />
  }

  return (
    <DomainProvider>
      <AuthProvider>
        <Router>
          <Routes>
            <Route path="/login" element={<Login />} />
            
            <Route path="/" element={<Layout />}>
              <Route index element={<Navigate to="/capital" replace />} />
              
              <Route path="/backtest" element={
                <PrivateRoute>
                  <Backtest />
                </PrivateRoute>
              } />
              
              <Route path="/capital" element={<Capital />} />
            </Route>
            
            <Route path="/deposit" element={
              <PublicRoute>
                <Capital />
              </PublicRoute>
            } />
            
            <Route path="/withdrawal" element={
              <PublicRoute>
                <Capital />
              </PublicRoute>
            } />
          </Routes>
        </Router>
      </AuthProvider>
    </DomainProvider>
  )
}

export default App
