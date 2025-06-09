/**
 * Comprehensive JavaScript fix for AUTOBOT login form and layout issues
 * This script fixes both the login form method/action and ensures main content visibility
 */

(function() {
    console.log("AUTOBOT Login and Layout Fix starting");
    fixLoginAndLayout();
    
    document.addEventListener('DOMContentLoaded', function() {
        console.log("AUTOBOT Login and Layout Fix on DOMContentLoaded");
        fixLoginAndLayout();
        
        setTimeout(fixLoginAndLayout, 500);
        setTimeout(fixLoginAndLayout, 1000);
    });
    
    setInterval(fixLoginAndLayout, 2000);
})();

function fixLoginAndLayout() {
    fixLoginForm();
    
    fixLayoutStructure();
}

function fixLoginForm() {
    console.log("Fixing login form...");
    const loginForm = document.querySelector('form');
    
    if (loginForm) {
        if (!loginForm.getAttribute('method') || !loginForm.getAttribute('action')) {
            loginForm.setAttribute('method', 'post');
            loginForm.setAttribute('action', '/login');
            console.log("Login form method and action set successfully");
        }
        
        const inputs = loginForm.querySelectorAll('input');
        inputs.forEach(input => {
            if (input.id === 'username' && !input.name) {
                input.name = 'username';
            }
            if (input.id === 'password' && !input.name) {
                input.name = 'password';
            }
            if (input.id === 'license_key' && !input.name) {
                input.name = 'license_key';
            }
        });
    } else {
        console.log("Login form not found");
    }
}

function fixLayoutStructure() {
    console.log("Fixing layout structure...");
    
    document.documentElement.style.setProperty('--sidebar-width', '250px');
    document.documentElement.style.setProperty('--primary-color', '#00ff9d');
    document.documentElement.style.setProperty('--bg-color', '#121212');
    document.documentElement.style.setProperty('--card-bg-color', '#1e1e1e');
    document.documentElement.style.setProperty('--text-color', '#ffffff');
    
    const body = document.body;
    if (!body) return;
    
    Object.assign(body.style, {
        display: 'flex',
        flexDirection: 'row',
        margin: '0',
        padding: '0',
        overflowX: 'hidden',
        backgroundColor: '#121212',
        color: '#ffffff'
    });
    
    let sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        Object.assign(sidebar.style, {
            width: '250px',
            position: 'fixed',
            height: '100vh',
            zIndex: '20',
            overflowY: 'auto',
            backgroundColor: '#121212',
            borderRight: '1px solid #2a2a2a'
        });
    }
    
    let mainContent = document.querySelector('.main-content');
    if (!mainContent) {
        mainContent = document.createElement('div');
        mainContent.className = 'main-content';
        
        if (sidebar) {
            const nonSidebarContent = Array.from(body.children).filter(el => 
                el !== sidebar && !el.classList.contains('sidebar'));
            
            mainContent.append(...nonSidebarContent);
        } else {
            const allContent = Array.from(body.children);
            mainContent.append(...allContent);
        }
        
        body.appendChild(mainContent);
    }
    
    Object.assign(mainContent.style, {
        marginLeft: sidebar ? '250px' : '0',
        padding: '20px',
        minHeight: '100vh',
        width: sidebar ? 'calc(100% - 250px)' : '100%',
        boxSizing: 'border-box',
        flex: '1',
        overflowX: 'hidden',
        display: 'block',
        position: 'relative',
        zIndex: '10',
        backgroundColor: '#121212',
        visibility: 'visible',
        opacity: '1'
    });
    
    const containers = document.querySelectorAll('.container, .container-fluid');
    containers.forEach(container => {
        Object.assign(container.style, {
            width: '100%',
            maxWidth: '100%',
            display: 'block',
            visibility: 'visible',
            opacity: '1'
        });
    });
    
    const logoImages = document.querySelectorAll('.logo img');
    logoImages.forEach(img => {
        Object.assign(img.style, {
            height: '60px',
            width: 'auto',
            maxHeight: '60px',
            marginRight: '15px'
        });
    });
    
    const allElements = document.querySelectorAll('*');
    allElements.forEach(el => {
        if (!el.closest('.sidebar') && !el.classList.contains('hidden') && !el.classList.contains('d-none')) {
            el.style.visibility = 'visible';
            el.style.opacity = '1';
            
            const computedStyle = window.getComputedStyle(el);
            if (computedStyle.display === 'none') {
                el.style.display = 'block';
            }
        }
    });
    
    console.log("Layout structure fixed");
}
