/**
 * Direct JavaScript fix for login form submission
 * This script ensures the login form has the correct method and action attributes
 * and handles form submission directly via JavaScript
 */

(function() {
    console.log("AUTOBOT Login Form Direct Fix starting");
    
    fixLoginForm();
    
    document.addEventListener('DOMContentLoaded', function() {
        console.log("AUTOBOT Login Form Direct Fix on DOMContentLoaded");
        fixLoginForm();
        
        setTimeout(fixLoginForm, 500);
        setTimeout(fixLoginForm, 1000);
    });
})();

function fixLoginForm() {
    console.log("Fixing login form submission...");
    
    const loginForm = document.querySelector('form');
    if (!loginForm) {
        console.log("Login form not found");
        return;
    }
    
    loginForm.setAttribute('method', 'post');
    loginForm.setAttribute('action', '/login');
    console.log("Login form method and action set to POST /login");
    
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
    
    loginForm.onsubmit = function(event) {
        event.preventDefault();
        
        const username = loginForm.querySelector('#username').value;
        const password = loginForm.querySelector('#password').value;
        const licenseKey = loginForm.querySelector('#license_key').value;
        
        console.log("Form submission intercepted, sending POST request to /login");
        
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);
        formData.append('license_key', licenseKey);
        
        fetch('/login', {
            method: 'POST',
            body: formData,
            redirect: 'follow'
        })
        .then(response => {
            if (response.redirected) {
                window.location.href = response.url;
            } else {
                return response.text().then(text => {
                    if (text.includes('Invalid credentials')) {
                        window.location.href = '/login?error=Invalid+credentials';
                    } else {
                        window.location.href = '/dashboard';
                    }
                });
            }
        })
        .catch(error => {
            console.error('Error during login:', error);
            window.location.href = '/login?error=Server+error';
        });
    };
    
    const loginButton = loginForm.querySelector('button[type="submit"]');
    if (loginButton) {
        loginButton.onclick = function(event) {
            if (!loginForm.onsubmit) {
                return;
            }
            
            loginForm.onsubmit(new Event('submit'));
        };
    }
    
    console.log("Login form submission handler installed");
}
