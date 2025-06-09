/**
 * Direct JavaScript fix for login form submission
 * This script ensures the form has the correct method and action attributes
 * and handles form submission directly via JavaScript
 */

// Function to fix the login form
function fixLoginForm() {
    console.log("Fixing login form...");
    
    // Find the login form
    const loginForm = document.querySelector('form');
    
    if (!loginForm) {
        console.error("No form found on the page!");
        return;
    }
    
    console.log("Original form attributes:", {
        method: loginForm.method,
        action: loginForm.action,
        enctype: loginForm.enctype
    });
    
    // Set the correct method and action
    loginForm.method = "post";
    loginForm.action = "/login";
    loginForm.enctype = "application/x-www-form-urlencoded";
    
    console.log("Updated form attributes:", {
        method: loginForm.method,
        action: loginForm.action,
        enctype: loginForm.enctype
    });
    
    // Add event listener to handle form submission
    loginForm.addEventListener('submit', function(event) {
        event.preventDefault();
        
        // Get form data
        const username = document.querySelector('input[name="username"]').value;
        const password = document.querySelector('input[name="password"]').value;
        const licenseKey = document.querySelector('input[name="license_key"]').value;
        
        console.log("Submitting form with data:", { username, password: "********", licenseKey: "********" });
        
        // Create form data object
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);
        formData.append('license_key', licenseKey);
        
        // Submit the form via fetch API
        fetch('/login', {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
            redirect: 'follow'
        })
        .then(response => {
            console.log("Response status:", response.status);
            if (response.redirected) {
                console.log("Redirecting to:", response.url);
                window.location.href = response.url;
            } else if (response.ok) {
                console.log("Login successful, redirecting to dashboard");
                window.location.href = "/dashboard/";
            } else {
                console.error("Login failed:", response.statusText);
                alert("Login failed: " + response.statusText);
            }
        })
        .catch(error => {
            console.error("Error during login:", error);
            alert("Error during login: " + error.message);
        });
    });
    
    // Also fix the login button click handler
    const loginButton = document.querySelector('button[type="submit"]') || 
                        document.querySelector('.login-button') || 
                        document.querySelector('#login-button');
    
    if (loginButton) {
        console.log("Found login button:", loginButton);
        loginButton.addEventListener('click', function(event) {
            if (event.target !== this) return;
            console.log("Login button clicked, submitting form");
            loginForm.dispatchEvent(new Event('submit'));
        });
    }
}

// Run the fix when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', fixLoginForm);

// Also try to run it immediately in case the DOM is already loaded
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    fixLoginForm();
}
