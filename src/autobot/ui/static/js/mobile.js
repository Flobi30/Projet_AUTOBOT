/**
 * Mobile-specific JavaScript for AUTOBOT
 * Handles responsive behavior and mobile interactions
 */

document.addEventListener('DOMContentLoaded', function() {
  initMobileNav();
  
  initCollapsibleSections();
  
  handleOrientationChanges();
  
  initMobileCharts();
  
  initTouchGestures();
});

/**
 * Initialize mobile navigation
 */
function initMobileNav() {
  const menuToggle = document.querySelector('.menu-toggle');
  const navMenu = document.querySelector('.nav-menu');
  
  if (menuToggle && navMenu) {
    menuToggle.addEventListener('click', function() {
      navMenu.classList.toggle('active');
      menuToggle.classList.toggle('active');
    });
    
    document.addEventListener('click', function(event) {
      if (!navMenu.contains(event.target) && !menuToggle.contains(event.target)) {
        navMenu.classList.remove('active');
        menuToggle.classList.remove('active');
      }
    });
  }
  
  const bottomNavItems = document.querySelectorAll('.bottom-nav-item');
  
  bottomNavItems.forEach(item => {
    item.addEventListener('click', function() {
      bottomNavItems.forEach(navItem => navItem.classList.remove('active'));
      this.classList.add('active');
    });
  });
}

/**
 * Initialize collapsible sections for mobile
 */
function initCollapsibleSections() {
  const collapsibleHeaders = document.querySelectorAll('.collapsible-header');
  
  collapsibleHeaders.forEach(header => {
    header.addEventListener('click', function() {
      const content = this.nextElementSibling;
      
      this.classList.toggle('active');
      
      if (content.style.maxHeight) {
        content.style.maxHeight = null;
      } else {
        content.style.maxHeight = content.scrollHeight + 'px';
      }
    });
  });
}

/**
 * Handle orientation changes
 */
function handleOrientationChanges() {
  window.addEventListener('orientationchange', function() {
    setTimeout(function() {
      if (window.autobotCharts) {
        Object.values(window.autobotCharts).forEach(chart => {
          if (chart && typeof chart.resize === 'function') {
            chart.resize();
          }
        });
      }
      
      adjustUIForOrientation();
    }, 200);
  });
}

/**
 * Adjust UI elements based on orientation
 */
function adjustUIForOrientation() {
  const isLandscape = window.innerWidth > window.innerHeight;
  const dashboardPanels = document.querySelectorAll('.dashboard-panel');
  
  if (isLandscape) {
    const panelGrid = document.querySelector('.panel-grid');
    if (panelGrid) {
      panelGrid.style.flexDirection = 'row';
      panelGrid.style.flexWrap = 'wrap';
    }
    
    dashboardPanels.forEach(panel => {
      panel.style.width = 'calc(50% - 10px)';
    });
  } else {
    const panelGrid = document.querySelector('.panel-grid');
    if (panelGrid) {
      panelGrid.style.flexDirection = 'column';
    }
    
    dashboardPanels.forEach(panel => {
      panel.style.width = '100%';
    });
  }
}

/**
 * Initialize mobile-specific charts
 * Simplifies charts for better mobile performance
 */
function initMobileCharts() {
  if (!window.autobotCharts) return;
  
  Object.values(window.autobotCharts).forEach(chart => {
    if (chart && chart.options) {
      if (chart.options.animation) {
        chart.options.animation.duration = 0;
      }
      
      if (chart.options.tooltips) {
        chart.options.tooltips.enabled = false;
        chart.options.tooltips.intersect = false;
      }
      
      if (chart.data && chart.data.datasets) {
        chart.data.datasets.forEach(dataset => {
          if (dataset.pointRadius) {
            dataset.pointRadius = 2;
          }
          if (dataset.pointHoverRadius) {
            dataset.pointHoverRadius = 3;
          }
        });
      }
      
      chart.update();
    }
  });
}

/**
 * Initialize touch gestures for mobile
 */
function initTouchGestures() {
  let touchStartX = 0;
  let touchEndX = 0;
  
  document.addEventListener('touchstart', function(event) {
    touchStartX = event.changedTouches[0].screenX;
  }, false);
  
  document.addEventListener('touchend', function(event) {
    touchEndX = event.changedTouches[0].screenX;
    handleSwipe();
  }, false);
  
  function handleSwipe() {
    const swipeThreshold = 100;
    
    if (touchEndX < touchStartX - swipeThreshold) {
      const nextTab = document.querySelector('.tab.active').nextElementSibling;
      if (nextTab) {
        switchTab(nextTab.dataset.tab);
      }
    }
    
    if (touchEndX > touchStartX + swipeThreshold) {
      const prevTab = document.querySelector('.tab.active').previousElementSibling;
      if (prevTab) {
        switchTab(prevTab.dataset.tab);
      }
    }
  }
  
  function switchTab(tabId) {
    const tabs = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabs.forEach(tab => tab.classList.remove('active'));
    tabContents.forEach(content => content.classList.remove('active'));
    
    document.querySelector(`.tab[data-tab="${tabId}"]`).classList.add('active');
    document.querySelector(`.tab-content[data-tab="${tabId}"]`).classList.add('active');
  }
}
