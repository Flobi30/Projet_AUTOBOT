console.log("Executing direct dashboard fix");

function injectCSS() {
  const style = document.createElement('style');
  style.textContent = `
    /* Reset body structure */
    body {
      display: flex !important;
      flex-direction: row !important;
      margin: 0 !important;
      padding: 0 !important;
      background-color: #121212 !important;
      color: white !important;
      font-family: 'Roboto', sans-serif !important;
      min-height: 100vh !important;
      width: 100% !important;
      overflow-x: hidden !important;
    }
    
    /* Force sidebar visibility */
    nav, .sidebar, [class*="sidebar"], [id*="sidebar"] {
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
    
    /* Create main content container if it doesn't exist */
    .dashboard-content-container {
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
    header, div:not(nav):not(.sidebar), p, span, a:not(nav a):not(.sidebar a), 
    button, input, select, textarea, table, tr, td, th {
      visibility: visible !important;
      opacity: 1 !important;
      display: block !important;
    }
    
    /* Force header visibility */
    header, .header {
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
      margin-bottom: 20px !important;
      border-bottom: 1px solid #333 !important;
      padding-bottom: 10px !important;
    }
    
    /* Force button display */
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
    
    /* Force input display */
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
  `;
  document.head.appendChild(style);
  console.log("CSS injected");
}

function restructureDOM() {
  console.log("Restructuring DOM");
  
  const sidebar = document.querySelector('nav');
  
  const contentContainer = document.createElement('div');
  contentContainer.className = 'dashboard-content-container';
  
  const bodyChildren = Array.from(document.body.children);
  
  bodyChildren.forEach(child => {
    if (child !== sidebar && 
        child.tagName !== 'SCRIPT' && 
        child.tagName !== 'STYLE' && 
        !child.classList.contains('sidebar') &&
        !child.classList.contains('dashboard-content-container')) {
      
      const clonedNode = child.cloneNode(true);
      contentContainer.appendChild(clonedNode);
      
      child.style.display = 'none';
    }
  });
  
  document.body.appendChild(contentContainer);
  
  const debugInfo = document.createElement('div');
  debugInfo.style.backgroundColor = '#333';
  debugInfo.style.padding = '10px';
  debugInfo.style.margin = '10px 0';
  debugInfo.style.borderRadius = '4px';
  debugInfo.innerHTML = `
    <h3 style="color: #00ff9d;">Dashboard Debug Info</h3>
    <p>Content container created with ${contentContainer.children.length} children</p>
    <p>Sidebar elements: ${sidebar ? sidebar.children.length : 'Not found'}</p>
    <p>Body direct children: ${document.body.children.length}</p>
    <p>Timestamp: ${new Date().toISOString()}</p>
  `;
  contentContainer.prepend(debugInfo);
  
  console.log("DOM restructured");
}

injectCSS();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', restructureDOM);
} else {
  restructureDOM();
}

setTimeout(() => {
  console.log("Running delayed fix");
  restructureDOM();
}, 1000);

const indicator = document.createElement('div');
indicator.style.position = 'fixed';
indicator.style.bottom = '10px';
indicator.style.right = '10px';
indicator.style.backgroundColor = '#00ff9d';
indicator.style.color = '#121212';
indicator.style.padding = '5px 10px';
indicator.style.borderRadius = '4px';
indicator.style.zIndex = '9999';
indicator.textContent = 'Dashboard Fix Active';
document.body.appendChild(indicator);
