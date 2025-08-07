import React from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { useDomain } from '../contexts/DomainContext'

const Layout: React.FC = () => {
  const { user, logout } = useAuth()
  const { isPublicDomain } = useDomain()
  const location = useLocation()

  const isActive = (path: string) => location.pathname === path

  if (isPublicDomain) {
    return (
      <div className="app-container">
        <div className="main-content" style={{ marginLeft: 0 }}>
          <header className="content-header">
            <h2 className="neon-text">AUTOBOT Capital</h2>
          </header>
          <div className="content-body">
            <Outlet />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="app-container">
      <div className="sidebar">
        <div className="logo-container" style={{ padding: '20px', textAlign: 'center' }}>
          <h1 className="neon-text">AUTOBOT</h1>
        </div>
        <nav className="nav-menu" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          <Link 
            to="/capital" 
            className={`nav-item ${isActive('/capital') ? 'active' : ''}`}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              padding: '15px 20px', 
              color: 'var(--text-color)', 
              textDecoration: 'none',
              backgroundColor: isActive('/capital') ? 'rgba(0, 255, 157, 0.1)' : 'transparent'
            }}
          >
            <i className="fas fa-coins" style={{ marginRight: '10px' }}></i>
            <span>Capital</span>
          </Link>
          <Link 
            to="/backtest" 
            className={`nav-item ${isActive('/backtest') ? 'active' : ''}`}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              padding: '15px 20px', 
              color: 'var(--text-color)', 
              textDecoration: 'none',
              backgroundColor: isActive('/backtest') ? 'rgba(0, 255, 157, 0.1)' : 'transparent'
            }}
          >
            <i className="fas fa-flask" style={{ marginRight: '10px' }}></i>
            <span>Backtest</span>
          </Link>
        </nav>
        <div className="user-info" style={{ position: 'absolute', bottom: '20px', left: '20px', right: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '10px' }}>
            <i className="fas fa-user" style={{ marginRight: '10px', color: 'var(--primary-color)' }}></i>
            <div>
              <div style={{ color: 'var(--text-color)', fontWeight: 'bold' }}>{user?.username}</div>
              <div style={{ color: 'var(--text-color)', fontSize: '0.8em' }}>
                {user?.role === 'admin' ? 'Administrateur' : 'Utilisateur'}
              </div>
            </div>
          </div>
          <button 
            onClick={logout}
            className="btn btn-primary"
            style={{ width: '100%', fontSize: '0.9em' }}
          >
            Déconnexion
          </button>
        </div>
      </div>

      <div className="main-content">
        <header className="content-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2 className="neon-text">
            {location.pathname === '/backtest' && 'Backtest'}
            {location.pathname === '/capital' && 'Gestion du Capital'}
          </h2>
        </header>
        <div className="content-body">
          <Outlet />
        </div>
      </div>
    </div>
  )
}

export default Layout
