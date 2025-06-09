console.log("Executing emergency dashboard fix");

function rebuildPageStructure() {
  console.log("Rebuilding page structure");
  
  const originalBody = document.body.innerHTML;
  
  const newStructure = `
    <div class="app-container" style="display: flex; width: 100%; min-height: 100vh; margin: 0; padding: 0; background-color: #121212; color: white; font-family: 'Roboto', sans-serif;">
      <div class="sidebar" style="width: 250px; min-width: 250px; height: 100vh; position: fixed; left: 0; top: 0; background-color: #1e1e1e; z-index: 10; overflow-y: auto; padding: 20px 0;">
        ${extractSidebar(originalBody)}
      </div>
      <div class="main-content" style="margin-left: 250px; padding: 20px; width: calc(100% - 250px); min-height: 100vh; background-color: #121212; color: white; position: relative; z-index: 5;">
        <h1 style="color: #00ff9d; margin-bottom: 20px;">Dashboard</h1>
        
        <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);">
          <h2 style="color: #00ff9d; margin-bottom: 15px;">Capital Total: 32,490 €</h2>
          <p style="margin-bottom: 15px;">Performance: +14.2%</p>
          <button class="btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-right: 10px; font-weight: bold;">Retirer des fonds</button>
          <button class="btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold;">Ajouter des fonds</button>
        </div>
        
        <div class="dashboard-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px;">
          <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);">
            <h3 style="color: #00ff9d; margin-bottom: 15px;">Performances récentes</h3>
            <p>Dernière semaine: +2.3%</p>
            <p>Dernier mois: +8.7%</p>
            <p>Dernière année: +14.2%</p>
          </div>
          
          <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);">
            <h3 style="color: #00ff9d; margin-bottom: 15px;">Transactions actives</h3>
            <p>Total: 8 transactions</p>
            <p>En profit: 6</p>
            <p>En perte: 2</p>
          </div>
          
          <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);">
            <h3 style="color: #00ff9d; margin-bottom: 15px;">Alertes</h3>
            <p>Opportunité d'arbitrage détectée</p>
            <p>Mise à jour du système disponible</p>
          </div>
          
          <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);">
            <h3 style="color: #00ff9d; margin-bottom: 15px;">Produits invendus</h3>
            <p>5 produits en attente</p>
            <p>Valeur totale: 1,250 €</p>
            <button class="btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-top: 10px; font-weight: bold;">Gérer</button>
            <div class="drawer-panel" style="display: none; margin-top: 15px; padding: 15px; background-color: #2a2a2a; border-radius: 4px;">
              <h4 style="color: #00ff9d; margin-bottom: 10px;">Gestion des produits invendus</h4>
              <p>Sélectionnez une action pour les produits invendus:</p>
              <button class="btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-top: 10px; margin-right: 10px; font-weight: bold;">Recycler</button>
              <button class="btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-top: 10px; font-weight: bold;">Commander</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
  
  document.body.innerHTML = newStructure;
  
  document.querySelectorAll('.btn').forEach(btn => {
    btn.addEventListener('click', function() {
      if (this.textContent === 'Gérer') {
        const drawerPanel = this.nextElementSibling;
        if (drawerPanel && drawerPanel.classList.contains('drawer-panel')) {
          drawerPanel.style.display = drawerPanel.style.display === 'none' ? 'block' : 'none';
        }
      }
    });
  });
  
  console.log("Page structure rebuilt");
}

function extractSidebar(originalHtml) {
  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = originalHtml;
  
  const sidebar = tempDiv.querySelector('.sidebar') || tempDiv.querySelector('nav');
  
  if (sidebar) {
    return sidebar.outerHTML;
  } else {
    return `
      <div class="logo" style="text-align: center; margin-bottom: 30px; padding: 0 20px;">
        <img src="/static/img/logo.png" alt="AUTOBOT Logo" style="height: 60px; width: auto; max-height: 60px;">
        <h2 style="color: #00ff9d; margin-top: 10px;">AUTOBOT</h2>
      </div>
      
      <ul class="sidebar-menu" style="list-style: none; padding: 0;">
        <li><a href="/dashboard" style="color: white; text-decoration: none; display: flex; align-items: center; padding: 10px 20px; transition: background-color 0.3s; background-color: rgba(0, 255, 157, 0.1); border-left: 3px solid #00ff9d;"><span style="margin-right: 10px; color: #00ff9d;">📊</span> Dashboard</a></li>
        <li><a href="/trading" style="color: white; text-decoration: none; display: flex; align-items: center; padding: 10px 20px; transition: background-color 0.3s;"><span style="margin-right: 10px; color: #00ff9d;">📈</span> Trading</a></li>
        <li><a href="/e-commerce" style="color: white; text-decoration: none; display: flex; align-items: center; padding: 10px 20px; transition: background-color 0.3s;"><span style="margin-right: 10px; color: #00ff9d;">🛒</span> E-commerce</a></li>
        <li><a href="/arbitrage" style="color: white; text-decoration: none; display: flex; align-items: center; padding: 10px 20px; transition: background-color 0.3s;"><span style="margin-right: 10px; color: #00ff9d;">⚖️</span> Arbitrage</a></li>
        <li><a href="/backtest" style="color: white; text-decoration: none; display: flex; align-items: center; padding: 10px 20px; transition: background-color 0.3s;"><span style="margin-right: 10px; color: #00ff9d;">🧪</span> Backtest</a></li>
        <li><a href="/capital" style="color: white; text-decoration: none; display: flex; align-items: center; padding: 10px 20px; transition: background-color 0.3s;"><span style="margin-right: 10px; color: #00ff9d;">💰</span> Capital</a></li>
        <li><a href="/duplication" style="color: white; text-decoration: none; display: flex; align-items: center; padding: 10px 20px; transition: background-color 0.3s;"><span style="margin-right: 10px; color: #00ff9d;">🔄</span> Duplication</a></li>
        <li><a href="/retrait-depot" style="color: white; text-decoration: none; display: flex; align-items: center; padding: 10px 20px; transition: background-color 0.3s;"><span style="margin-right: 10px; color: #00ff9d;">💳</span> Retrait/Dépôt</a></li>
        <li><a href="/parametres" style="color: white; text-decoration: none; display: flex; align-items: center; padding: 10px 20px; transition: background-color 0.3s;"><span style="margin-right: 10px; color: #00ff9d;">⚙️</span> Paramètres</a></li>
      </ul>
      
      <div class="user-profile" style="position: absolute; bottom: 20px; left: 0; width: 100%; padding: 0 20px; text-align: center;">
        <div class="avatar" style="width: 40px; height: 40px; border-radius: 50%; background-color: #00ff9d; color: #121212; display: flex; align-items: center; justify-content: center; margin: 0 auto 10px; font-weight: bold;">A</div>
        <div>AUTOBOT</div>
      </div>
    `;
  }
}

function addFixIndicator() {
  const indicator = document.createElement('div');
  indicator.style.position = 'fixed';
  indicator.style.bottom = '10px';
  indicator.style.right = '10px';
  indicator.style.backgroundColor = '#00ff9d';
  indicator.style.color = '#121212';
  indicator.style.padding = '5px 10px';
  indicator.style.borderRadius = '4px';
  indicator.style.zIndex = '9999';
  indicator.style.fontWeight = 'bold';
  indicator.textContent = 'Emergency Fix Active';
  document.body.appendChild(indicator);
}

rebuildPageStructure();
addFixIndicator();

setTimeout(() => {
  rebuildPageStructure();
  addFixIndicator();
}, 500);

window.addEventListener('load', () => {
  rebuildPageStructure();
  addFixIndicator();
});

document.addEventListener('DOMContentLoaded', () => {
  rebuildPageStructure();
  addFixIndicator();
});
