document.addEventListener('DOMContentLoaded', function() {
  setTimeout(() => {
    const depositButton = document.querySelector('button:contains("Effectuer un Dépôt")');
    if (depositButton) {
      depositButton.addEventListener('click', async function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        const buttonText = this.querySelector('span');
        const buttonIcon = this.querySelector('svg');
        if (buttonText) buttonText.textContent = 'Préparation...';
        if (buttonIcon) buttonIcon.classList.add('animate-spin');
        this.disabled = true;
        
        try {
          const response = await fetch('/api/stripe/create-checkout-session', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              amount: 5000, // 50€ in cents
              currency: 'eur',
            }),
          });
          
          const data = await response.json();
          console.log("Stripe session created:", data);
          
          if (data.url) {
            window.location.href = data.url;
          } else {
            console.error("No redirect URL provided by the server");
            alert("Erreur: Impossible de rediriger vers la page de paiement");
          }
        } catch (error) {
          console.error("Error creating checkout session:", error);
          alert("Erreur lors de la création de la session de paiement");
        }
        
        setTimeout(() => {
          if (buttonText) buttonText.textContent = 'Effectuer un Dépôt';
          if (buttonIcon) buttonIcon.classList.remove('animate-spin');
          this.disabled = false;
        }, 2000);
      });
    }
  }, 1000);
});
