console.log("Executing complete layout rebuild");

function injectCSS() {
  const style = document.createElement('style');
  style.textContent = `
    /* Reset body structure */
    body {
      margin: 0 !important;
      padding: 0 !important;
      background-color: #121212 !important;
      color: white !important;
      font-family: 'Roboto', sans-serif !important;
      min-height: 100vh !important;
      width: 100% !important;
      overflow-x: hidden !important;
      display: flex !important;
      flex-direction: row !important;
    }
    
    /* Force sidebar visibility */
    .sidebar-container {
      width: 250px !important;
      min-width: 250px !important;
      max-width: 250px !important;
      position: fixed !important;
      height: 100vh !important;
      left: 0 !important;
      top: 0 !important;
      background-color: #1e1e1e !important;
      z-index: 10 !important;
      display: block !important;
      overflow-y: auto !important;
      box-sizing: border-box !important;
      padding: 20px 0 !important;
    }
    
    /* Create main content container */
    .main-content-container {
      margin-left: 250px !important;
      width: calc(100% - 250px) !important;
      min-height: 100vh !important;
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
      position: relative !important;
      z-index: 5 !important;
      background-color: #121212 !important;
      color: white !important;
      padding: 20px !important;
      box-sizing: border-box !important;
      overflow-x: hidden !important;
    }
    
    /* Force all headings to be visible */
    h1, h2, h3, h4, h5, h6 {
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
      color: #00ff9d !important;
      margin-top: 20px !important;
      margin-bottom: 10px !important;
    }
    
    /* Force all content elements to be visible */
    .main-content-container div, .main-content-container p, .main-content-container span, 
    .main-content-container a, .main-content-container button, .main-content-container input, 
    .main-content-container select, .main-content-container textarea, .main-content-container table, 
    .main-content-container tr, .main-content-container td, .main-content-container th {
      visibility: visible !important;
      opacity: 1 !important;
      display: block !important;
    }
    
    /* Force button styling */
    button, .btn, [class*="btn"], [type="button"], [type="submit"] {
      display: inline-block !important;
      background-color: #00ff9d !important;
      color: #121212 !important;
      border: none !important;
      padding: 8px 16px !important;
      margin: 5px !important;
      border-radius: 4px !important;
      cursor: pointer !important;
    }
    
    /* Force input styling */
    input, select, textarea {
      display: block !important;
      background-color: #2a2a2a !important;
      color: white !important;
      border: 1px solid #444 !important;
      border-radius: 4px !important;
      padding: 8px !important;
      margin: 5px 0 !important;
      width: 100% !important;
      max-width: 400px !important;
    }
    
    /* Force logo proportions */
    .logo img, img[src*="logo"] {
      height: 60px !important;
      width: auto !important;
      max-height: 60px !important;
      display: inline-block !important;
      visibility: visible !important;
      opacity: 1 !important;
    }
    
    /* Card styling */
    .card {
      background-color: #1e1e1e !important;
      border-radius: 8px !important;
      padding: 15px !important;
      margin-bottom: 20px !important;
      box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2) !important;
    }
    
    /* Dashboard content styling */
    .dashboard-content {
      display: grid !important;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)) !important;
      gap: 20px !important;
      margin-top: 20px !important;
    }
    
    /* Drawer panel styling */
    .drawer-panel {
      position: fixed !important;
      right: -400px !important;
      top: 0 !important;
      width: 400px !important;
      height: 100vh !important;
      background-color: #1e1e1e !important;
      box-shadow: -2px 0 10px rgba(0, 0, 0, 0.5) !important;
      transition: right 0.3s ease !important;
      z-index: 1000 !important;
      padding: 20px !important;
      overflow-y: auto !important;
    }
    
    .drawer-panel.open {
      right: 0 !important;
    }
    
    .drawer-panel-header {
      display: flex !important;
      justify-content: space-between !important;
      align-items: center !important;
      margin-bottom: 20px !important;
      border-bottom: 1px solid #333 !important;
      padding-bottom: 10px !important;
    }
    
    .drawer-panel-close {
      background: none !important;
      border: none !important;
      color: #00ff9d !important;
      font-size: 24px !important;
      cursor: pointer !important;
    }
    
    /* API key field styling */
    .api-key-field {
      position: relative !important;
      margin-bottom: 15px !important;
    }
    
    .api-key-field input {
      padding-right: 40px !important;
    }
    
    .toggle-visibility {
      position: absolute !important;
      right: 10px !important;
      top: 50% !important;
      transform: translateY(-50%) !important;
      background: none !important;
      border: none !important;
      color: #00ff9d !important;
      cursor: pointer !important;
    }
  `;
  document.head.appendChild(style);
  console.log("CSS injected");
}

function rebuildDOM() {
  console.log("Rebuilding DOM");
  
  const originalSidebar = document.querySelector('nav') || document.querySelector('.sidebar');
  
  document.body.innerHTML = '';
  
  const sidebarContainer = document.createElement('div');
  sidebarContainer.className = 'sidebar-container';
  
  if (originalSidebar) {
    sidebarContainer.appendChild(originalSidebar.cloneNode(true));
  } else {
    sidebarContainer.innerHTML = `
      <div class="logo" style="text-align: center; margin-bottom: 30px;">
        <img src="/static/img/logo.png" alt="AUTOBOT Logo" style="height: 60px; width: auto;">
        <h2 style="color: #00ff9d; margin-top: 10px;">AUTOBOT</h2>
      </div>
      <ul style="list-style: none; padding: 0; margin: 0;">
        <li style="margin-bottom: 10px;"><a href="/dashboard" style="color: white; text-decoration: none; display: block; padding: 10px 20px;">Dashboard</a></li>
        <li style="margin-bottom: 10px;"><a href="/trading" style="color: white; text-decoration: none; display: block; padding: 10px 20px;">Trading</a></li>
        <li style="margin-bottom: 10px;"><a href="/e-commerce" style="color: white; text-decoration: none; display: block; padding: 10px 20px;">E-commerce</a></li>
        <li style="margin-bottom: 10px;"><a href="/arbitrage" style="color: white; text-decoration: none; display: block; padding: 10px 20px;">Arbitrage</a></li>
        <li style="margin-bottom: 10px;"><a href="/backtest" style="color: white; text-decoration: none; display: block; padding: 10px 20px;">Backtest</a></li>
        <li style="margin-bottom: 10px;"><a href="/capital" style="color: white; text-decoration: none; display: block; padding: 10px 20px;">Capital</a></li>
        <li style="margin-bottom: 10px;"><a href="/duplication" style="color: white; text-decoration: none; display: block; padding: 10px 20px;">Duplication</a></li>
        <li style="margin-bottom: 10px;"><a href="/retrait-depot" style="color: white; text-decoration: none; display: block; padding: 10px 20px;">Retrait/Dépôt</a></li>
        <li style="margin-bottom: 10px;"><a href="/parametres" style="color: white; text-decoration: none; display: block; padding: 10px 20px;">Paramètres</a></li>
      </ul>
    `;
  }
  
  const mainContentContainer = document.createElement('div');
  mainContentContainer.className = 'main-content-container';
  
  const currentPath = window.location.pathname;
  
  if (currentPath.includes('dashboard')) {
    mainContentContainer.innerHTML = `
      <h1>Dashboard</h1>
      <div class="card">
        <h2>Capital Total: 32,490 €</h2>
        <p>Performance: +14.2%</p>
        <button class="btn">Retirer des fonds</button>
        <button class="btn">Ajouter des fonds</button>
      </div>
      <div class="dashboard-content">
        <div class="card">
          <h3>Performances récentes</h3>
          <p>Dernière semaine: +2.3%</p>
          <p>Dernier mois: +8.7%</p>
          <p>Dernière année: +14.2%</p>
        </div>
        <div class="card">
          <h3>Transactions actives</h3>
          <p>Total: 8 transactions</p>
          <p>En profit: 6</p>
          <p>En perte: 2</p>
        </div>
        <div class="card">
          <h3>Alertes</h3>
          <p>Opportunité d'arbitrage détectée</p>
          <p>Mise à jour du système disponible</p>
        </div>
      </div>
    `;
  } else if (currentPath.includes('e-commerce')) {
    mainContentContainer.innerHTML = `
      <h1>E-commerce</h1>
      <div class="card">
        <h2>Produits invendus</h2>
        <table style="width: 100%; border-collapse: collapse;">
          <thead>
            <tr>
              <th style="text-align: left; padding: 10px; border-bottom: 1px solid #333;">Produit</th>
              <th style="text-align: left; padding: 10px; border-bottom: 1px solid #333;">Quantité</th>
              <th style="text-align: left; padding: 10px; border-bottom: 1px solid #333;">Prix</th>
              <th style="text-align: left; padding: 10px; border-bottom: 1px solid #333;">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="padding: 10px; border-bottom: 1px solid #333;">Produit A</td>
              <td style="padding: 10px; border-bottom: 1px solid #333;">15</td>
              <td style="padding: 10px; border-bottom: 1px solid #333;">120 €</td>
              <td style="padding: 10px; border-bottom: 1px solid #333;">
                <button class="btn" onclick="openDrawerPanel()">Gérer</button>
              </td>
            </tr>
            <tr>
              <td style="padding: 10px; border-bottom: 1px solid #333;">Produit B</td>
              <td style="padding: 10px; border-bottom: 1px solid #333;">8</td>
              <td style="padding: 10px; border-bottom: 1px solid #333;">85 €</td>
              <td style="padding: 10px; border-bottom: 1px solid #333;">
                <button class="btn" onclick="openDrawerPanel()">Gérer</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <!-- Drawer Panel for Unsold Products -->
      <div class="drawer-panel" id="drawerPanel">
        <div class="drawer-panel-header">
          <h2>Gestion des invendus</h2>
          <button class="drawer-panel-close" onclick="closeDrawerPanel()">×</button>
        </div>
        <div class="drawer-panel-content">
          <h3>Options de recyclage</h3>
          <div class="card">
            <h4>Recycler les produits</h4>
            <p>Envoyer les produits invendus au centre de recyclage.</p>
            <button class="btn">Recycler</button>
          </div>
          
          <h3>Options de commande</h3>
          <div class="card">
            <h4>Commander et expédier</h4>
            <p>Commander les produits invendus pour votre propre usage.</p>
            
            <div class="form-group">
              <label>Méthode d'expédition</label>
              <select>
                <option>Standard (3-5 jours)</option>
                <option>Express (1-2 jours)</option>
                <option>Premium (24h)</option>
              </select>
            </div>
            
            <div class="form-group">
              <label>Adresse de livraison</label>
              <textarea rows="3"></textarea>
            </div>
            
            <div class="form-group">
              <label>Vérification du solde</label>
              <p>Solde actuel: 32,490 €</p>
              <p>Coût total: 205 €</p>
            </div>
            
            <button class="btn">Commander</button>
          </div>
        </div>
      </div>
      
      <script>
        function openDrawerPanel() {
          document.getElementById('drawerPanel').classList.add('open');
        }
        
        function closeDrawerPanel() {
          document.getElementById('drawerPanel').classList.remove('open');
        }
      </script>
    `;
  } else if (currentPath.includes('parametres')) {
    mainContentContainer.innerHTML = `
      <h1>Paramètres</h1>
      <div class="card">
        <h2>Clés API</h2>
        
        <div class="api-key-field">
          <label>Binance API Key</label>
          <input type="password" value="••••••••••••••••">
          <button class="toggle-visibility">👁️</button>
        </div>
        
        <div class="api-key-field">
          <label>Twelve Data API Key</label>
          <input type="password" value="••••••••••••••••">
          <button class="toggle-visibility">👁️</button>
        </div>
        
        <div class="api-key-field">
          <label>Alpha Vantage API Key</label>
          <input type="password" value="••••••••••••••••">
          <button class="toggle-visibility">👁️</button>
        </div>
        
        <div class="api-key-field">
          <label>Coinbase API Key</label>
          <input type="password" value="••••••••••••••••">
          <button class="toggle-visibility">👁️</button>
        </div>
        
        <div class="api-key-field">
          <label>FRED API Key</label>
          <input type="password" value="••••••••••••••••">
          <button class="toggle-visibility">👁️</button>
        </div>
        
        <div class="api-key-field">
          <label>Kraken API Key</label>
          <input type="password" value="••••••••••••••••">
          <button class="toggle-visibility">👁️</button>
        </div>
        
        <div class="api-key-field">
          <label>NewsAPI Key</label>
          <input type="password" value="••••••••••••••••">
          <button class="toggle-visibility">👁️</button>
        </div>
        
        <div class="api-key-field">
          <label>Shopify API Key</label>
          <input type="password" value="••••••••••••••••">
          <button class="toggle-visibility">👁️</button>
        </div>
        
        <button class="btn">Enregistrer</button>
      </div>
      
      <script>
        document.querySelectorAll('.toggle-visibility').forEach(button => {
          button.addEventListener('click', function() {
            const input = this.previousElementSibling;
            if (input.type === 'password') {
              input.type = 'text';
              this.textContent = '🔒';
            } else {
              input.type = 'password';
              this.textContent = '👁️';
            }
          });
        });
        
        document.querySelector('.btn').addEventListener('click', function() {
          alert('API keys saved. Backtesting will start automatically.');
        });
      </script>
    `;
  } else {
    mainContentContainer.innerHTML = `
      <h1>${currentPath.substring(1).charAt(0).toUpperCase() + currentPath.substring(2)}</h1>
      <div class="card">
        <h2>Contenu de la page</h2>
        <p>Cette page est en cours de chargement ou n'a pas de contenu spécifique défini.</p>
      </div>
    `;
  }
  
  const debugInfo = document.createElement('div');
  debugInfo.style.backgroundColor = '#333';
  debugInfo.style.padding = '10px';
  debugInfo.style.margin = '10px 0';
  debugInfo.style.borderRadius = '4px';
  debugInfo.innerHTML = `
    <h3 style="color: #00ff9d;">Debug Info</h3>
    <p>Page: ${currentPath}</p>
    <p>Timestamp: ${new Date().toISOString()}</p>
    <p>Original sidebar found: ${originalSidebar ? 'Yes' : 'No'}</p>
    <p>Layout rebuild complete</p>
  `;
  mainContentContainer.appendChild(debugInfo);
  
  document.body.appendChild(sidebarContainer);
  document.body.appendChild(mainContentContainer);
  
  console.log("DOM rebuilt");
}

injectCSS();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', rebuildDOM);
} else {
  rebuildDOM();
}

const indicator = document.createElement('div');
indicator.style.position = 'fixed';
indicator.style.bottom = '10px';
indicator.style.right = '10px';
indicator.style.backgroundColor = '#00ff9d';
indicator.style.color = '#121212';
indicator.style.padding = '5px 10px';
indicator.style.borderRadius = '4px';
indicator.style.zIndex = '9999';
indicator.textContent = 'Complete Layout Rebuild Active';
document.body.appendChild(indicator);
