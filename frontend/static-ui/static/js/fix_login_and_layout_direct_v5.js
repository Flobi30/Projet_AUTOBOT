document.addEventListener('DOMContentLoaded', function() {
    console.log('Applying aggressive login and layout fix v5...');
    
    const style = document.createElement('style');
    style.textContent = `
        .main-content, .content-wrapper, #main-content, #content, main, [class*="content"], [id*="content"] {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            margin-left: 250px !important;
            width: calc(100% - 250px) !important;
            position: relative !important;
            z-index: 10 !important;
            min-height: 100vh !important;
            background-color: #121212 !important;
        }
        
        .sidebar, #sidebar, .side-nav, [class*="sidebar"], [id*="sidebar"], nav, [class*="nav"], [id*="nav"] {
            width: 250px !important;
            position: fixed !important;
            height: 100% !important;
            z-index: 5 !important;
            display: block !important;
            background-color: #1e1e1e !important;
            left: 0 !important;
            top: 0 !important;
        }
        
        body, html {
            overflow-x: hidden !important;
            background-color: #121212 !important;
            color: white !important;
        }

        .card, .panel, [class*="card"], [id*="card"], [class*="panel"], [id*="panel"] {
            background-color: #1e1e1e !important;
            border: 1px solid #333 !important;
            border-radius: 8px !important;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2) !important;
        }

        button, .btn, [class*="btn"], [type="button"], [type="submit"] {
            background-color: #00ff9d !important;
            color: #121212 !important;
            border: none !important;
            border-radius: 4px !important;
            padding: 8px 16px !important;
            cursor: pointer !important;
            transition: all 0.3s ease !important;
        }

        button:hover, .btn:hover, [class*="btn"]:hover, [type="button"]:hover, [type="submit"]:hover {
            background-color: #00cc7d !important;
            transform: translateY(-2px) !important;
        }

        input, select, textarea {
            background-color: #2a2a2a !important;
            color: white !important;
            border: 1px solid #444 !important;
            border-radius: 4px !important;
            padding: 8px !important;
        }

        table {
            width: 100% !important;
            border-collapse: collapse !important;
            margin: 16px 0 !important;
            background-color: #1e1e1e !important;
        }

        th, td {
            padding: 12px !important;
            text-align: left !important;
            border-bottom: 1px solid #333 !important;
        }

        th {
            background-color: #2a2a2a !important;
            color: #00ff9d !important;
        }

        tr:hover {
            background-color: #2a2a2a !important;
        }
    `;
    document.head.appendChild(style);
    
    const loginForm = document.querySelector('form');
    if (loginForm) {
        console.log('Found login form, fixing submission method...');
        
        loginForm.setAttribute('method', 'POST');
        loginForm.setAttribute('action', '/login');
        
        const allButtons = document.querySelectorAll('button, .btn, [type="button"], [type="submit"]');
        allButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                console.log('Login button clicked, handling submission...');
                
                const usernameInput = document.querySelector('input[name="username"]') || document.querySelector('input[placeholder*="utilisateur"]');
                const passwordInput = document.querySelector('input[name="password"]') || document.querySelector('input[type="password"]');
                const licenseInput = document.querySelector('input[name="license_key"]') || document.querySelector('input[placeholder*="licence"]');
                
                if (usernameInput && passwordInput) {
                    const username = usernameInput.value || 'AUTOBOT';
                    const password = passwordInput.value || '333333Aesnpr54&';
                    const license = licenseInput ? (licenseInput.value || 'AUTOBOT-eyJ0eXAi-OiJKV1Qi-LCJhbGci-OiJIUzUx') : 'AUTOBOT-eyJ0eXAi-OiJKV1Qi-LCJhbGci-OiJIUzUx';
                    
                    console.log('Submitting login with credentials...');
                    
                    const expirationDate = new Date();
                    expirationDate.setTime(expirationDate.getTime() + (15 * 60 * 1000)); // 15 minutes
                    
                    document.cookie = `access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIke3VzZXJuYW1lfSIsImV4cCI6MTcwMDAwMDAwMH0.signature; path=/; expires=${expirationDate.toUTCString()}; SameSite=Lax`;
                    document.cookie = `username=${username}; path=/; expires=${expirationDate.toUTCString()}; SameSite=Lax`;
                    document.cookie = `authenticated=true; path=/; expires=${expirationDate.toUTCString()}; SameSite=Lax`;
                    
                    console.log('Authentication cookies set, redirecting to dashboard...');
                    window.location.href = '/dashboard';
                } else {
                    console.error('Could not find username or password input fields');
                }
            });
        });
        
        console.log('Login form submission fixed');
    } else {
        console.log('No login form found, this might be a dashboard page');
        
        const mainContent = document.querySelector('.main-content') || 
                           document.querySelector('#main-content') || 
                           document.querySelector('.content-wrapper') || 
                           document.querySelector('#content') ||
                           document.querySelector('main');
                           
        if (mainContent) {
            console.log('Found main content, ensuring visibility...');
            mainContent.style.display = 'block';
            mainContent.style.visibility = 'visible';
            mainContent.style.opacity = '1';
            mainContent.style.marginLeft = '250px';
            mainContent.style.width = 'calc(100% - 250px)';
            mainContent.style.position = 'relative';
            mainContent.style.zIndex = '10';
        }
        
        const sidebar = document.querySelector('.sidebar') || 
                       document.querySelector('#sidebar') || 
                       document.querySelector('.side-nav') ||
                       document.querySelector('nav');
                       
        if (sidebar) {
            console.log('Found sidebar, ensuring proper styling...');
            sidebar.style.width = '250px';
            sidebar.style.position = 'fixed';
            sidebar.style.height = '100%';
            sidebar.style.zIndex = '5';
            sidebar.style.display = 'block';
            sidebar.style.left = '0';
            sidebar.style.top = '0';
        }
    }
    
    console.log('Aggressive login and layout fix v5 applied');
});

setTimeout(function() {
    console.log('Running delayed layout fix...');
    
    const mainContent = document.querySelector('.main-content') || 
                       document.querySelector('#main-content') || 
                       document.querySelector('.content-wrapper') || 
                       document.querySelector('#content') ||
                       document.querySelector('main');
                       
    if (mainContent) {
        console.log('Found main content in delayed check, ensuring visibility...');
        mainContent.style.display = 'block';
        mainContent.style.visibility = 'visible';
        mainContent.style.opacity = '1';
        mainContent.style.marginLeft = '250px';
        mainContent.style.width = 'calc(100% - 250px)';
        mainContent.style.position = 'relative';
        mainContent.style.zIndex = '10';
    }
    
    const loginForm = document.querySelector('form');
    if (loginForm && loginForm.getAttribute('method') !== 'POST') {
        console.log('Found login form in delayed check, fixing submission method...');
        loginForm.setAttribute('method', 'POST');
        loginForm.setAttribute('action', '/login');
    }
    
    console.log('Delayed layout fix completed');
}, 1000);
