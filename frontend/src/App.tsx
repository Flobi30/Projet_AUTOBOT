import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Sidebar from './components/layout/Sidebar';
import LiveTrading from './pages/LiveTrading';
import Backtest from './pages/Backtest';
import Capital from './pages/Capital';
import Analytics from './pages/Analytics';

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#1a1a1a',
            color: '#fff',
            border: '1px solid #3a3a3a',
          },
        }}
      />
      <Router>
        <div className="flex">
          <Sidebar isOpen={sidebarOpen} setIsOpen={setSidebarOpen} />
          <main className="flex-1 lg:ml-64 transition-all duration-300">
            <Routes>
              <Route path="/" element={<LiveTrading />} />
              <Route path="/trading" element={<LiveTrading />} />
              <Route path="/backtest" element={<Backtest />} />
              <Route path="/capital" element={<Capital />} />
              <Route path="/analytics" element={<Analytics />} />
            </Routes>
          </main>
        </div>
      </Router>
    </div>
  );
}

export default App;
