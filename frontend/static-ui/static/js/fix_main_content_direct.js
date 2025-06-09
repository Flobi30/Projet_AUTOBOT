console.log("Executing main content direct fix");

function injectCSS() {
  const style = document.createElement('style');
  style.textContent = `
    /* Force main content visibility */
    body > *:not(nav):not(.sidebar):not(script):not(style) {
      margin-left: 250px !important;
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
      position: relative !important;
      z-index: 5 !important;
    }
    
    /* Force header visibility */
    header {
      margin-left: 250px !important;
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
      padding: 20px !important;
      background-color: #1e1e1e !important;
      border-bottom: 1px solid #333 !important;
    }
    
    /* Force all headings to be visible */
    h1, h2, h3, h4, h5, h6 {
      display: block !important;
      visibility: visible !important;
      opacity: 1 !important;
      color: #00ff9d !important;
    }
  `;
  document.head.appendChild(style);
  console.log("CSS injected");
}

function forceMainContentVisibility() {
  console.log("Forcing main content visibility");
  
  if (!document.querySelector('.main-content-container')) {
    const mainContentContainer = document.createElement('div');
    mainContentContainer.className = 'main-content-container';
    mainContentContainer.style.marginLeft = '250px';
    mainContentContainer.style.padding = '20px';
    mainContentContainer.style.display = 'block';
    mainContentContainer.style.visibility = 'visible';
    mainContentContainer.style.opacity = '1';
    
    const bodyChildren = Array.from(document.body.children);
    bodyChildren.forEach(child => {
      if (child.tagName !== 'NAV' && 
          !child.classList.contains('sidebar') && 
          child.tagName !== 'SCRIPT' && 
          child.tagName !== 'STYLE' &&
          !child.classList.contains('main-content-container')) {
        mainContentContainer.appendChild(child.cloneNode(true));
      }
    });
    
    document.body.appendChild(mainContentContainer);
  }
  
  document.querySelectorAll('body > *:not(nav):not(.sidebar):not(script):not(style)').forEach(el => {
    el.style.marginLeft = '250px';
    el.style.display = 'block';
    el.style.visibility = 'visible';
    el.style.opacity = '1';
    el.style.position = 'relative';
    el.style.zIndex = '5';
  });
  
  document.querySelectorAll('header').forEach(header => {
    header.style.marginLeft = '250px';
    header.style.display = 'block';
    header.style.visibility = 'visible';
    header.style.opacity = '1';
  });
  
  document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(heading => {
    heading.style.display = 'block';
    heading.style.visibility = 'visible';
    heading.style.opacity = '1';
    heading.style.color = '#00ff9d';
  });
  
  console.log("Main content visibility forced");
}

injectCSS();
forceMainContentVisibility();

const indicator = document.createElement('div');
indicator.style.position = 'fixed';
indicator.style.bottom = '10px';
indicator.style.right = '10px';
indicator.style.backgroundColor = '#00ff9d';
indicator.style.color = '#121212';
indicator.style.padding = '5px 10px';
indicator.style.borderRadius = '4px';
indicator.style.zIndex = '9999';
indicator.textContent = 'Main Content Fix Active';
document.body.appendChild(indicator);

setTimeout(forceMainContentVisibility, 1000);
