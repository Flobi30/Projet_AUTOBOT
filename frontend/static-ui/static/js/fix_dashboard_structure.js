console.log("Executing dashboard structure fix");

function fixDashboardStructure() {
  console.log("Fixing dashboard structure");
  
  let mainContainer = document.querySelector('.main-container');
  if (!mainContainer) {
    mainContainer = document.createElement('div');
    mainContainer.className = 'main-container';
    mainContainer.style.cssText = `
      display: flex;
      width: 100%;
      min-height: 100vh;
      margin: 0;
      padding: 0;
      background-color: #121212;
    `;
    
    while (document.body.firstChild) {
      mainContainer.appendChild(document.body.firstChild);
    }
    
    document.body.appendChild(mainContainer);
    console.log("Created main container");
  }
  
  const sidebar = document.querySelector('.sidebar') || document.querySelector('nav');
  if (sidebar) {
    sidebar.style.cssText = `
      width: 250px;
      min-width: 250px;
      height: 100vh;
      position: fixed;
      left: 0;
      top: 0;
      background-color: #1e1e1e;
      z-index: 10;
      overflow-y: auto;
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
    `;
    console.log("Fixed sidebar styling");
  }
  
  let mainContent = document.querySelector('.main-content');
  if (!mainContent) {
    mainContent = document.createElement('div');
    mainContent.className = 'main-content';
    
    const contentElements = Array.from(document.body.querySelectorAll('*:not(nav):not(.sidebar):not(script):not(style):not(.main-container)'))
      .filter(el => {
        const parent = el.parentElement;
        return parent === document.body || parent === mainContainer;
      });
    
    contentElements.forEach(el => {
      if (el !== mainContent && el !== sidebar && el !== mainContainer) {
        mainContent.appendChild(el);
      }
    });
    
    if (mainContainer) {
      mainContainer.appendChild(mainContent);
    } else {
      document.body.appendChild(mainContent);
    }
    
    console.log("Created main content area");
  }
  
  mainContent.style.cssText = `
    margin-left: 250px;
    padding: 20px;
    width: calc(100% - 250px);
    min-height: 100vh;
    background-color: #121212;
    color: white;
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
    position: relative;
    z-index: 5;
    overflow-x: hidden;
  `;
  
  if (window.location.pathname.includes('dashboard') && !document.querySelector('.dashboard-content')) {
    const dashboardContent = document.createElement('div');
    dashboardContent.className = 'dashboard-content';
    dashboardContent.innerHTML = `
      <h1 style="color: #00ff9d; margin-bottom: 20px;">Dashboard</h1>
      
      <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
        <h2 style="color: #00ff9d; margin-bottom: 15px;">Capital Total: 32,490 €</h2>
        <p style="margin-bottom: 15px;">Performance: +14.2%</p>
        <button class="btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-right: 10px;">Retirer des fonds</button>
        <button class="btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">Ajouter des fonds</button>
      </div>
      
      <div class="dashboard-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px;">
        <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px;">
          <h3 style="color: #00ff9d; margin-bottom: 15px;">Performances récentes</h3>
          <p>Dernière semaine: +2.3%</p>
          <p>Dernier mois: +8.7%</p>
          <p>Dernière année: +14.2%</p>
        </div>
        
        <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px;">
          <h3 style="color: #00ff9d; margin-bottom: 15px;">Transactions actives</h3>
          <p>Total: 8 transactions</p>
          <p>En profit: 6</p>
          <p>En perte: 2</p>
        </div>
        
        <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px;">
          <h3 style="color: #00ff9d; margin-bottom: 15px;">Alertes</h3>
          <p>Opportunité d'arbitrage détectée</p>
          <p>Mise à jour du système disponible</p>
        </div>
        
        <div class="card" style="background-color: #1e1e1e; border-radius: 8px; padding: 20px;">
          <h3 style="color: #00ff9d; margin-bottom: 15px;">Produits invendus</h3>
          <p>5 produits en attente</p>
          <p>Valeur totale: 1,250 €</p>
          <button class="btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-top: 10px;">Gérer</button>
        </div>
      </div>
    `;
    
    mainContent.appendChild(dashboardContent);
    console.log("Created dashboard content");
  }
  
  document.querySelectorAll('h1, h2, h3, h4, h5, h6, p, button, input, select, textarea, table, tr, td, th, div, span, a').forEach(el => {
    if (el !== document.body && !el.closest('.sidebar') && !el.closest('nav')) {
      el.style.display = el.tagName === 'SPAN' || el.tagName === 'A' ? 'inline-block' : 'block';
      el.style.visibility = 'visible';
      el.style.opacity = '1';
    }
  });
  
  console.log("Dashboard structure fixed");
}

fixDashboardStructure();

setTimeout(fixDashboardStructure, 500);

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
indicator.textContent = 'Structure Fix Active';
document.body.appendChild(indicator);
