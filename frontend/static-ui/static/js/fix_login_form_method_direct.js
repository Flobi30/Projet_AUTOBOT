/**
 * Direct JavaScript fix for login form method in AUTOBOT.
 * This script ensures the login form uses POST method and handles form submission correctly.
 */

(function() {
    console.log('AUTOBOT login form method fix loaded');
    
    document.addEventListener('DOMContentLoaded', function() {
        const loginForm = document.querySelector('form');
        
        if (loginForm) {
            console.log('Login form found, applying method fix');
            
            loginForm.setAttribute('method', 'post');
            
            loginForm.setAttribute('action', '/login');
            
            console.log('Form method set to POST and action set to /login');
            
            loginForm.addEventListener('submit', function(event) {
                console.log('Form submitted with POST method');
            });
        } else {
            console.error('Login form not found');
        }
    });
})();
