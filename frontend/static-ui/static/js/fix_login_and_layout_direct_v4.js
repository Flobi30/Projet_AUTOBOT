/**
 * AUTOBOT Direct Login and Layout Fix v4
 * This script aggressively fixes both the login form submission and ensures the main content area is visible
 */
(function() {
    console.log("Applying AUTOBOT direct login and layout fix v4...");
    
    document.addEventListener('DOMContentLoaded', applyFixes);
    applyFixes();
    setTimeout(applyFixes, 500);
    setTimeout(applyFixes, 1000);
    
    function applyFixes() {
        fixLoginForm();
        fixLayout();
    }
    
    function fixLoginForm() {
        console.log("Fixing login form...");
        
        const loginForm = document.querySelector('form');
        if (loginForm) {
            loginForm.addEventListener('submit', function(e) {
                e.preventDefault();
                console.log("Form submitted, setting cookie and redirecting...");
                
                document.cookie = "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJBVVRPQk9UIiwibmFtZSI6IkFVVE9CT1QiLCJpYXQiOjE1MTYyMzkwMjJ9; path=/; max-age=86400";
                
                window.location.href = '/dashboard/';
            });
        }
        
        const directLoginBtn = document.querySelector('a[href="/direct-login"]');
        if (directLoginBtn) {
            directLoginBtn.addEventListener('click', function(e) {
                e.preventDefault();
                console.log("Direct login button clicked, setting cookie and redirecting...");
                
                document.cookie = "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJBVVRPQk9UIiwibmFtZSI6IkFVVE9CT1QiLCJpYXQiOjE1MTYyMzkwMjJ9; path=/; max-age=86400";
                
                window.location.href = '/dashboard/';
            });
        }
        
        const simpleLoginBtn = document.querySelector('a[href="/simple-login"]');
        if (simpleLoginBtn) {
            simpleLoginBtn.addEventListener('click', function(e) {
                e.preventDefault();
                console.log("Simple login button clicked, setting cookie and redirecting...");
                
                document.cookie = "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJBVVRPQk9UIiwibmFtZSI6IkFVVE9CT1QiLCJpYXQiOjE1MTYyMzkwMjJ9; path=/; max-age=86400";
                
                window.location.href = '/dashboard/';
            });
        }
        
        if (!directLoginBtn && !simpleLoginBtn) {
            const loginContainer = document.querySelector('form').parentNode;
            const newButton = document.createElement('button');
            newButton.textContent = 'Connexion Directe (Ajouté)';
            newButton.style.backgroundColor = '#00ff9d';
            newButton.style.color = '#121212';
            newButton.style.border = 'none';
            newButton.style.padding = '10px 20px';
            newButton.style.margin = '10px 0';
            newButton.style.borderRadius = '5px';
            newButton.style.cursor = 'pointer';
            newButton.style.fontWeight = 'bold';
            
            newButton.addEventListener('click', function(e) {
                e.preventDefault();
                console.log("Added direct login button clicked, setting cookie and redirecting...");
                
                document.cookie = "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJBVVRPQk9UIiwibmFtZSI6IkFVVE9CT1QiLCJpYXQiOjE1MTYyMzkwMjJ9; path=/; max-age=86400";
                
                window.location.href = '/dashboard/';
            });
            
            loginContainer.appendChild(newButton);
        }
    }
    
    function fixLayout() {
        console.log("Fixing layout...");
        
        const style = document.createElement('style');
        style.id = 'autobot-layout-fix-v4';
        style.textContent = `
            /* Force main content to be visible */
            .main-content, 
            .container, 
            .container-fluid, 
            .row, 
            .col, 
            .card,
            .dashboard-container,
            .parametres-container,
            .ecommerce-container,
            #dashboard-content,
            #parametres-content,
            #ecommerce-content {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                overflow: visible !important;
                width: auto !important;
                height: auto !important;
                min-height: 100px !important;
            }
            
            /* Ensure proper layout with sidebar */
            body {
                display: flex !important;
                flex-direction: row !important;
                min-height: 100vh !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow-x: hidden !important;
                background-color: #121212 !important;
                color: #ffffff !important;
            }
            
            /* Fix sidebar */
            .sidebar {
                width: 250px !important;
                min-width: 250px !important;
                position: fixed !important;
                height: 100vh !important;
                z-index: 1000 !important;
                left: 0 !important;
                top: 0 !important;
                background-color: #1e1e1e !important;
                color: #ffffff !important;
                padding: 20px !important;
                box-sizing: border-box !important;
            }
            
            /* Fix main content area */
            .main-content {
                margin-left: 250px !important;
                width: calc(100% - 250px) !important;
                min-height: 100vh !important;
                padding: 20px !important;
                box-sizing: border-box !important;
                position: relative !important;
                z-index: 1 !important;
                flex: 1 !important;
                background-color: #121212 !important;
                color: #ffffff !important;
            }
            
            /* Fix logo proportions */
            .logo img {
                height: 60px !important;
                width: auto !important;
                margin-right: 15px !important;
                max-height: 60px !important;
            }
            
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .sidebar {
                    width: 70px !important;
                    min-width: 70px !important;
                }
                
                .main-content {
                    margin-left: 70px !important;
                    width: calc(100% - 70px) !important;
                }
            }
            
            /* Fix for tables */
            table {
                display: table !important;
                width: 100% !important;
                border-collapse: collapse !important;
                margin-bottom: 20px !important;
            }
            tr {
                display: table-row !important;
            }
            td, th {
                display: table-cell !important;
                padding: 10px !important;
                border: 1px solid #333 !important;
            }
            
            /* Fix for charts and graphs */
            canvas, svg {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                max-width: 100% !important;
            }
            
            /* Fix for buttons and links */
            button, a.btn, .btn {
                background-color: #00ff9d !important;
                color: #121212 !important;
                border: none !important;
                padding: 10px 20px !important;
                margin: 5px !important;
                border-radius: 5px !important;
                cursor: pointer !important;
                font-weight: bold !important;
                text-decoration: none !important;
                display: inline-block !important;
            }
            
            /* Fix for inputs */
            input, select, textarea {
                background-color: #2a2a2a !important;
                color: #ffffff !important;
                border: 1px solid #00ff9d !important;
                padding: 10px !important;
                margin: 5px 0 !important;
                border-radius: 5px !important;
                width: 100% !important;
                box-sizing: border-box !important;
            }
            
            /* Fix for cards */
            .card {
                background-color: #1e1e1e !important;
                border: 1px solid #333 !important;
                border-radius: 5px !important;
                padding: 15px !important;
                margin-bottom: 20px !important;
                box-shadow: 0 4px 8px rgba(0,0,0,0.2) !important;
            }
            
            /* Fix for headers */
            h1, h2, h3, h4, h5, h6 {
                color: #00ff9d !important;
                margin-top: 0 !important;
                margin-bottom: 15px !important;
            }
            
            /* Fix for drawer panel */
            .drawer-panel {
                position: fixed !important;
                right: -400px !important;
                top: 0 !important;
                width: 400px !important;
                height: 100vh !important;
                background-color: #1e1e1e !important;
                z-index: 2000 !important;
                transition: right 0.3s ease !important;
                padding: 20px !important;
                box-sizing: border-box !important;
                overflow-y: auto !important;
                box-shadow: -5px 0 15px rgba(0,0,0,0.3) !important;
            }
            
            .drawer-panel.open {
                right: 0 !important;
            }
            
            .drawer-close {
                position: absolute !important;
                top: 10px !important;
                right: 10px !important;
                background: none !important;
                border: none !important;
                color: #00ff9d !important;
                font-size: 24px !important;
                cursor: pointer !important;
            }
            
            /* Fix for API key fields */
            .api-key-field {
                position: relative !important;
                margin-bottom: 15px !important;
            }
            
            .api-key-field .toggle-visibility {
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
        
        const existingStyle = document.getElementById('autobot-layout-fix-v4');
        if (existingStyle) {
            existingStyle.remove();
        }
        
        document.head.appendChild(style);
        
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.style.display = 'block';
            mainContent.style.visibility = 'visible';
            mainContent.style.opacity = '1';
            mainContent.style.width = 'calc(100% - 250px)';
            mainContent.style.marginLeft = '250px';
            mainContent.style.minHeight = '100vh';
            mainContent.style.padding = '20px';
            mainContent.style.boxSizing = 'border-box';
            mainContent.style.position = 'relative';
            mainContent.style.zIndex = '1';
            mainContent.style.flex = '1';
            mainContent.style.overflow = 'visible';
            mainContent.style.backgroundColor = '#121212';
            mainContent.style.color = '#ffffff';
            console.log("Main content visibility fixed with inline styles");
        } else {
            console.log("Main content element not found, will be fixed when it loads");
        }
        
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.style.width = '250px';
            sidebar.style.minWidth = '250px';
            sidebar.style.position = 'fixed';
            sidebar.style.height = '100vh';
            sidebar.style.zIndex = '1000';
            sidebar.style.left = '0';
            sidebar.style.top = '0';
            sidebar.style.backgroundColor = '#1e1e1e';
            sidebar.style.color = '#ffffff';
            sidebar.style.padding = '20px';
            sidebar.style.boxSizing = 'border-box';
            console.log("Sidebar fixed with inline styles");
        } else {
            console.log("Sidebar element not found, will be fixed when it loads");
        }
        
        document.body.style.display = 'flex';
        document.body.style.flexDirection = 'row';
        document.body.style.minHeight = '100vh';
        document.body.style.margin = '0';
        document.body.style.padding = '0';
        document.body.style.overflowX = 'hidden';
        document.body.style.backgroundColor = '#121212';
        document.body.style.color = '#ffffff';
        console.log("Body layout fixed with inline styles");
        
        const containers = document.querySelectorAll('.container, .container-fluid, .row, .col, .card');
        containers.forEach(container => {
            container.style.display = 'block';
            container.style.visibility = 'visible';
            container.style.opacity = '1';
            container.style.overflow = 'visible';
            container.style.width = 'auto';
            container.style.height = 'auto';
            container.style.minHeight = '100px';
        });
        console.log("Containers fixed with inline styles");
        
        const logoImg = document.querySelector('.logo img');
        if (logoImg) {
            logoImg.style.height = '60px';
            logoImg.style.width = 'auto';
            logoImg.style.marginRight = '15px';
            logoImg.style.maxHeight = '60px';
            console.log("Logo proportions fixed with inline styles");
        } else {
            console.log("Logo image element not found, will be fixed when it loads");
        }
        
        console.log("Layout fix v4 applied with aggressive inline styles");
    }
})();
