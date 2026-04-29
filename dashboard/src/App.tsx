import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Sidebar from './components/layout/Sidebar';


import Capital from './pages/Capital';

import Diagnostic from './pages/Diagnostic';
import Performance from './pages/Performance';
import QuantValidation from './pages/QuantValidation';

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
              <Route path="/" element={<Performance />} />
              <Route path="/performance" element={<Performance />} />
              <Route path="/capital" element={<Capital />} />
              <Route path="/diagnostic" element={<Diagnostic />} />
              <Route path="/quant-validation" element={<QuantValidation />} />
            </Routes>
          </main>
        </div>
      </Router>
    </div>
  );
}

export default App;
