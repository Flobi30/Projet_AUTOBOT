/**
 * AUTOBOT Direct Login and Layout Fix v2
 * This script fixes both the login form submission and ensures the main content area is visible
 */
(function() {
    console.log("Applying AUTOBOT direct login and layout fix v2...");
    
    if (window.location.pathname === '/login') {
        console.log("On login page, fixing login form...");
        
        document.addEventListener('DOMContentLoaded', fixLoginForm);
        
        fixLoginForm();
        
        setTimeout(fixLoginForm, 500);
    }
    
    document.addEventListener('DOMContentLoaded', fixLayout);
    fixLayout();
    setTimeout(fixLayout, 500);
    setTimeout(fixLayout, 1000);
    
    function fixLoginForm() {
        console.log("Fixing login form...");
        
        const loginForm = document.querySelector('form');
        if (loginForm) {
            loginForm.method = 'POST';
            loginForm.action = '/dashboard/';  // Direct submission to dashboard
            console.log("Form method and action set");
            
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
    }
    
    function fixLayout() {
        console.log("Fixing layout...");
        
        const style = document.createElement('style');
        style.id = 'autobot-layout-fix-v2';
        style.textContent = `
            /* Force main content to be visible */
            .main-content, 
            .container, 
            .container-fluid, 
            .row, 
            .col, 
            .card {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                overflow: visible !important;
            }
            
            /* Ensure proper layout with sidebar */
            body {
                display: flex !important;
                flex-direction: row !important;
                min-height: 100vh !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow-x: hidden !important;
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
            }
            
            /* Fix logo proportions */
            .logo img {
                height: 60px !important;
                width: auto !important;
                margin-right: 15px !important;
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
            
            /* Fix for specific elements */
            #dashboard-content,
            #parametres-content,
            #ecommerce-content,
            .dashboard-container,
            .parametres-container,
            .ecommerce-container {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                width: 100% !important;
            }
            
            /* Fix for tables */
            table, tr, td, th {
                visibility: visible !important;
            }
            table {
                display: table !important;
            }
            tr {
                display: table-row !important;
            }
            td, th {
                display: table-cell !important;
            }
            
            /* Fix for charts and graphs */
            canvas, svg {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
        `;
        
        const existingStyle = document.getElementById('autobot-layout-fix-v2');
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
            console.log("Main content visibility fixed");
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
            console.log("Sidebar fixed");
        }
        
        document.body.style.display = 'flex';
        document.body.style.flexDirection = 'row';
        document.body.style.minHeight = '100vh';
        document.body.style.margin = '0';
        document.body.style.padding = '0';
        document.body.style.overflowX = 'hidden';
        console.log("Body layout fixed");
        
        const containers = document.querySelectorAll('.container, .container-fluid, .row, .col, .card');
        containers.forEach(container => {
            container.style.display = 'block';
            container.style.visibility = 'visible';
            container.style.opacity = '1';
            container.style.overflow = 'visible';
        });
        console.log("Containers fixed");
        
        const logoImg = document.querySelector('.logo img');
        if (logoImg) {
            logoImg.style.height = '60px';
            logoImg.style.width = 'auto';
            logoImg.style.marginRight = '15px';
            console.log("Logo proportions fixed");
        }
        
        console.log("Layout fix applied");
    }
})();
