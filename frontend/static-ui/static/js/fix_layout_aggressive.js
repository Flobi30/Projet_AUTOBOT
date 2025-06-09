/**
 * Aggressive JavaScript fix for AUTOBOT layout issues
 * This script completely rebuilds the layout structure to ensure main content is visible
 */

(function() {
    console.log("AUTOBOT Aggressive Layout Fix starting");
    
    fixLayoutAggressively();
    
    document.addEventListener('DOMContentLoaded', function() {
        console.log("AUTOBOT Aggressive Layout Fix on DOMContentLoaded");
        fixLayoutAggressively();
    });
    
    setTimeout(fixLayoutAggressively, 500);
    setTimeout(fixLayoutAggressively, 1000);
    
    setInterval(fixLayoutAggressively, 2000);
})();

function fixLayoutAggressively() {
    console.log("Applying aggressive layout fix...");
    
    document.documentElement.style.setProperty('--sidebar-width', '250px');
    document.documentElement.style.setProperty('--primary-color', '#00ff9d');
    document.documentElement.style.setProperty('--bg-color', '#121212');
    document.documentElement.style.setProperty('--card-bg-color', '#1e1e1e');
    document.documentElement.style.setProperty('--text-color', '#ffffff');
    
    const body = document.body;
    if (!body) return;
    
    const originalContent = Array.from(body.children);
    
    body.innerHTML = '';
    Object.assign(body.style, {
        display: 'flex',
        flexDirection: 'row',
        margin: '0',
        padding: '0',
        overflowX: 'hidden',
        backgroundColor: '#121212',
        color: '#ffffff',
        minHeight: '100vh',
        width: '100%'
    });
    
    const sidebar = document.createElement('div');
    sidebar.className = 'sidebar';
    Object.assign(sidebar.style, {
        width: '250px',
        minWidth: '250px',
        position: 'fixed',
        height: '100vh',
        zIndex: '20',
        overflowY: 'auto',
        backgroundColor: '#121212',
        borderRight: '1px solid #2a2a2a',
        left: '0',
        top: '0',
        display: 'block',
        visibility: 'visible',
        opacity: '1'
    });
    
    const mainContent = document.createElement('div');
    mainContent.className = 'main-content';
    Object.assign(mainContent.style, {
        marginLeft: '250px',
        padding: '20px',
        minHeight: '100vh',
        width: 'calc(100% - 250px)',
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
    
    originalContent.forEach(element => {
        const clone = element.cloneNode(true);
        
        if (
            clone.classList && (
                clone.classList.contains('sidebar') || 
                clone.classList.contains('side-nav') ||
                clone.classList.contains('nav-sidebar') ||
                clone.id === 'sidebar' ||
                clone.querySelector('.sidebar, .side-nav, .nav-sidebar, #sidebar')
            )
        ) {
            sidebar.appendChild(clone);
        } else if (
            clone.classList && (
                clone.classList.contains('main-content') ||
                clone.classList.contains('content') ||
                clone.classList.contains('container') ||
                clone.classList.contains('container-fluid') ||
                clone.id === 'main-content' ||
                clone.id === 'content'
            )
        ) {
            mainContent.appendChild(clone);
        } else if (clone.tagName === 'SCRIPT' || clone.tagName === 'LINK' || clone.tagName === 'STYLE') {
            body.appendChild(clone);
        } else {
            mainContent.appendChild(clone);
        }
    });
    
    if (!sidebar.hasChildNodes()) {
        const potentialSidebar = mainContent.querySelector('.sidebar, .side-nav, .nav-sidebar, #sidebar');
        if (potentialSidebar) {
            sidebar.appendChild(potentialSidebar.cloneNode(true));
            potentialSidebar.remove();
        }
    }
    
    if (!sidebar.hasChildNodes()) {
        sidebar.innerHTML = `
            <div style="padding: 20px; color: #00ff9d;">
                <h3>AUTOBOT</h3>
                <div style="height: 1px; background-color: #2a2a2a; margin: 10px 0;"></div>
                <ul style="list-style: none; padding: 0;">
                    <li style="margin-bottom: 10px;"><a href="/dashboard" style="color: #00ff9d; text-decoration: none;">Dashboard</a></li>
                    <li style="margin-bottom: 10px;"><a href="/parametres" style="color: #00ff9d; text-decoration: none;">Paramètres</a></li>
                    <li style="margin-bottom: 10px;"><a href="/ecommerce" style="color: #00ff9d; text-decoration: none;">E-commerce</a></li>
                </ul>
            </div>
        `;
    }
    
    body.appendChild(sidebar);
    body.appendChild(mainContent);
    
    const logoImages = document.querySelectorAll('.logo img');
    logoImages.forEach(img => {
        Object.assign(img.style, {
            height: '60px',
            width: 'auto',
            maxHeight: '60px',
            marginRight: '15px'
        });
    });
    
    const cards = document.querySelectorAll('.card, .content-section');
    cards.forEach(card => {
        Object.assign(card.style, {
            backgroundColor: '#1e1e1e',
            border: '1px solid #2a2a2a',
            borderRadius: '8px',
            marginBottom: '20px',
            boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
            display: 'block',
            visibility: 'visible',
            opacity: '1'
        });
    });
    
    const mainContentElements = mainContent.querySelectorAll('*');
    mainContentElements.forEach(el => {
        if (!el.classList.contains('hidden') && !el.classList.contains('d-none')) {
            el.style.visibility = 'visible';
            el.style.opacity = '1';
            
            const computedStyle = window.getComputedStyle(el);
            if (computedStyle.display === 'none') {
                el.style.display = 'block';
            }
        }
    });
    
    console.log("Aggressive layout fix applied");
}
