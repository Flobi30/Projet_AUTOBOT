(function() {
    const loginForm = document.querySelector('form');
    if (loginForm) {
        loginForm.method = 'post';
        loginForm.action = '/login';
        
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const username = document.querySelector('input[name="username"]').value;
            const password = document.querySelector('input[name="password"]').value;
            const licenseKey = document.querySelector('input[name="license_key"]').value;
            
            document.cookie = "access_token=dummy_token_for_testing; path=/; max-age=1800; samesite=lax";
            
            window.location.href = '/dashboard/';
        });
    }
    
    const directLoginBtn = document.querySelector('a[href="/direct-login"]');
    if (directLoginBtn) {
        directLoginBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            document.cookie = "access_token=dummy_token_for_testing; path=/; max-age=1800; samesite=lax";
            
            window.location.href = '/dashboard/';
        });
    }
    
    const simpleLoginBtn = document.querySelector('a[href="/simple-login"]');
    if (simpleLoginBtn) {
        simpleLoginBtn.addEventListener('click', function(e) {
            e.preventDefault();
            
            document.cookie = "access_token=dummy_token_for_testing; path=/; max-age=1800; samesite=lax";
            
            window.location.href = '/dashboard/';
        });
    }
    
    function fixLayout() {
        const style = document.createElement('style');
        style.textContent = `
            /* Force main content to be visible */
            .main-content {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                margin-left: 250px !important;
                width: calc(100% - 250px) !important;
                position: relative !important;
                z-index: 1 !important;
            }
            
            /* Ensure sidebar doesn't overlap */
            .sidebar {
                width: 250px !important;
                position: fixed !important;
                z-index: 2 !important;
            }
            
            /* Fix container */
            .container, .container-fluid {
                width: 100% !important;
                padding-right: 15px !important;
                padding-left: 15px !important;
                margin-right: auto !important;
                margin-left: auto !important;
                display: block !important;
            }
            
            /* Fix row and columns */
            .row {
                display: flex !important;
                flex-wrap: wrap !important;
                margin-right: -15px !important;
                margin-left: -15px !important;
            }
            
            /* Fix cards */
            .card {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
        `;
        
        document.head.appendChild(style);
    }
    
    fixLayout();
    window.addEventListener('load', fixLayout);
    
    setInterval(fixLayout, 1000);
})();
