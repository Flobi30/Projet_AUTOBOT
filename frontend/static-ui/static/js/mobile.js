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
  // Removed menu-toggle functionality since mobile templates use direct navigation
  
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
      const isActive = this.classList.contains('active');
      
      if (isActive) {
        this.classList.remove('active');
        content.style.maxHeight = null;
      } else {
        this.classList.add('active');
        content.style.maxHeight = content.scrollHeight + "px";
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
      if (window.Chart) {
        Chart.helpers.each(Chart.instances, function(instance) {
          instance.resize();
        });
      }
    }, 500);
  });
}

/**
 * Initialize mobile-optimized charts
 */
function initMobileCharts() {
  if (typeof Chart !== 'undefined') {
    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false;
    
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.elements.point.radius = 2;
    Chart.defaults.elements.line.borderWidth = 1;
  }
}

/**
 * Initialize touch gestures
 */
function initTouchGestures() {
  let startY = 0;
  let currentY = 0;
  let isScrolling = false;
  
  document.addEventListener('touchstart', function(e) {
    startY = e.touches[0].clientY;
    isScrolling = false;
  }, { passive: true });
  
  document.addEventListener('touchmove', function(e) {
    currentY = e.touches[0].clientY;
    
    if (Math.abs(currentY - startY) > 10) {
      isScrolling = true;
    }
  }, { passive: true });
  
  document.addEventListener('touchend', function(e) {
    if (!isScrolling) {
      const target = e.target.closest('.card, .metric-card');
      if (target) {
        target.classList.add('touch-feedback');
        setTimeout(() => {
          target.classList.remove('touch-feedback');
        }, 150);
      }
    }
  }, { passive: true });
}

/**
 * Mobile-specific form handling
 */
function initMobileFormHandling() {
  const forms = document.querySelectorAll('form');
  
  forms.forEach(form => {
    form.addEventListener('submit', function(e) {
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Envoi en cours...';
        
        setTimeout(() => {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Sauvegarder';
        }, 2000);
      }
    });
  });
}

/**
 * Initialize mobile-specific features
 */
if (window.innerWidth <= 768) {
  document.addEventListener('DOMContentLoaded', function() {
    initMobileFormHandling();
  });
}
