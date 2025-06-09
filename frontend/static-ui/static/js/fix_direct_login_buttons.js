/**
 * AUTOBOT Direct Login Button Fix
 * This script fixes the direct login buttons to properly redirect to the dashboard
 */
(function() {
    console.log("Applying AUTOBOT direct login button fix...");
    
    document.addEventListener('DOMContentLoaded', function() {
        fixDirectLoginButtons();
    });
    
    fixDirectLoginButtons();
    
    function fixDirectLoginButtons() {
        const directLoginBtn = document.querySelector('a[href="/direct-login"]');
        if (directLoginBtn) {
            console.log("Found direct login button, applying fix...");
            
            directLoginBtn.addEventListener('click', function(e) {
                e.preventDefault();
                console.log("Direct login button clicked, setting cookie and redirecting...");
                
                document.cookie = "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJBVVRPQk9UIiwibmFtZSI6IkFVVE9CT1QiLCJpYXQiOjE1MTYyMzkwMjJ9; path=/; max-age=86400";
                
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = '/dashboard/';
                form.style.display = 'none';
                
                const usernameInput = document.createElement('input');
                usernameInput.type = 'hidden';
                usernameInput.name = 'username';
                usernameInput.value = 'AUTOBOT';
                form.appendChild(usernameInput);
                
                const passwordInput = document.createElement('input');
                passwordInput.type = 'hidden';
                passwordInput.name = 'password';
                passwordInput.value = '333333Aesnpr54&';
                form.appendChild(passwordInput);
                
                const licenseInput = document.createElement('input');
                licenseInput.type = 'hidden';
                licenseInput.name = 'license_key';
                licenseInput.value = 'AUTOBOT-eyJ0eXAi-OiJKV1Qi-LCJhbGci-OiJIUzUx';
                form.appendChild(licenseInput);
                
                document.body.appendChild(form);
                form.submit();
            });
            
            console.log("Direct login button fix applied");
        } else {
            console.log("Direct login button not found, will try again later");
            setTimeout(fixDirectLoginButtons, 500);
        }
        
        const simpleLoginBtn = document.querySelector('a[href="/simple-login"]');
        if (simpleLoginBtn) {
            console.log("Found simple login button, applying fix...");
            
            simpleLoginBtn.addEventListener('click', function(e) {
                e.preventDefault();
                console.log("Simple login button clicked, setting cookie and redirecting...");
                
                document.cookie = "access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJBVVRPQk9UIiwibmFtZSI6IkFVVE9CT1QiLCJpYXQiOjE1MTYyMzkwMjJ9; path=/; max-age=86400";
                
                window.location.href = '/dashboard/';
            });
            
            console.log("Simple login button fix applied");
        }
    }
})();
