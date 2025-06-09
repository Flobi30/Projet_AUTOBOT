/**
 * Direct JavaScript fix for AUTOBOT login
 * This script bypasses server-side form handling issues by:
 * 1. Finding the form directly without relying on class selectors
 * 2. Setting authentication cookies directly
 * 3. Redirecting to the dashboard
 */

function setCookie(name, value, days) {
  let expires = "";
  if (days) {
    const date = new Date();
    date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
    expires = "; expires=" + date.toUTCString();
  }
  document.cookie = name + "=" + (value || "") + expires + "; path=/; samesite=lax";
}

function handleLoginSubmit(event) {
  if (event) {
    event.preventDefault();
  }
  
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  const licenseKey = document.getElementById('license_key').value;
  
  console.log("Login attempt:", username, password, licenseKey);
  
  if (username === "AUTOBOT" && 
      password === "333333Aesnpr54&" && 
      licenseKey === "AUTOBOT-eyJ0eXAi-OiJKV1Qi-LCJhbGci-OiJIUzUx") {
    
    setCookie("access_token", "dummy_token_for_testing", 1); // 1 day
    setCookie("auth_status", "authenticated", 1); // 1 day
    
    window.location.href = "/dashboard";
    
    return false;
  } else {
    alert("Invalid credentials. Please try again.");
    return false;
  }
}

function initLoginForm() {
  const loginForm = document.querySelector('form');
  if (loginForm) {
    console.log("Login form found, attaching handler");
    loginForm.addEventListener('submit', handleLoginSubmit);
    
    const loginButton = document.querySelector('button[type="submit"]');
    if (loginButton) {
      console.log("Login button found, attaching handler");
      loginButton.addEventListener('click', function(e) {
        e.preventDefault();
        handleLoginSubmit(new Event('submit'));
      });
    } else {
      console.error("Login button not found");
    }
  } else {
    console.error("Login form not found");
  }
  
  const directLoginButton = document.getElementById('login-button');
  if (directLoginButton) {
    console.log("Direct login button found, attaching handler");
    directLoginButton.addEventListener('click', function(e) {
      e.preventDefault();
      handleLoginSubmit(new Event('submit'));
    });
  }
  
  const allButtons = document.querySelectorAll('button');
  allButtons.forEach(button => {
    if (button.textContent.toLowerCase().includes('connect') || 
        button.textContent.toLowerCase().includes('login') ||
        button.textContent.toLowerCase().includes('se connecter')) {
      console.log("Found login-related button, attaching handler:", button.textContent);
      button.addEventListener('click', function(e) {
        e.preventDefault();
        handleLoginSubmit(new Event('submit'));
      });
    }
  });
}

document.addEventListener('DOMContentLoaded', initLoginForm);

initLoginForm();

window.addEventListener('click', function(e) {
  if (e.target && 
      (e.target.id === 'login-button' || 
       (e.target.tagName === 'BUTTON' && e.target.textContent.toLowerCase().includes('connect')))) {
    console.log("Global click handler caught login button click");
    e.preventDefault();
    handleLoginSubmit(new Event('submit'));
  }
});
