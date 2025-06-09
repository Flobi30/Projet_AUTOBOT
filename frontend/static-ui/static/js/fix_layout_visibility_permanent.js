document.addEventListener('DOMContentLoaded', function() {
    console.log('Applying permanent layout visibility fix...');
    
    const style = document.createElement('style');
    style.textContent = `
        /* Main content area fix */
        .main-content, main, [class*="content"], [id*="content"] {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            margin-left: 250px !important;
            width: calc(100% - 250px) !important;
            position: relative !important;
            z-index: 5 !important;
            background-color: #121212 !important;
            color: white !important;
            padding: 20px !important;
            min-height: 100vh !important;
            box-sizing: border-box !important;
        }
        
        /* Sidebar fix */
        .sidebar, nav, [class*="sidebar"], [id*="sidebar"] {
            width: 250px !important;
            position: fixed !important;
            height: 100vh !important;
            left: 0 !important;
            top: 0 !important;
            background-color: #1e1e1e !important;
            z-index: 10 !important;
            display: block !important;
            overflow-y: auto !important;
        }
        
        /* Body fix */
        body, html {
            overflow-x: hidden !important;
            background-color: #121212 !important;
            color: white !important;
            margin: 0 !important;
            padding: 0 !important;
            font-family: 'Roboto', sans-serif !important;
        }

        /* Header fix */
        header, .header {
            margin-left: 250px !important;
            width: calc(100% - 250px) !important;
            padding: 20px !important;
            background-color: #1e1e1e !important;
            border-bottom: 1px solid #333 !important;
            display: block !important;
            position: relative !important;
        }
        
        /* Card elements fix */
        .card, .panel, [class*="card"], [id*="panel"] {
            background-color: #1e1e1e !important;
            border: 1px solid #333 !important;
            border-radius: 8px !important;
            margin: 10px 0 !important;
            padding: 15px !important;
            display: block !important;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2) !important;
        }
        
        /* Heading colors */
        h2, h3, h4 {
            color: #00ff9d !important;
            margin-top: 20px !important;
            margin-bottom: 10px !important;
        }
        
        /* Button styling */
        button, .btn, [class*="btn"], [type="button"], [type="submit"] {
            background-color: #00ff9d !important;
            color: #121212 !important;
            border: none !important;
            padding: 8px 16px !important;
            margin: 5px !important;
            border-radius: 4px !important;
            cursor: pointer !important;
            transition: all 0.3s ease !important;
        }
        
        /* Input styling */
        input, select, textarea {
            background-color: #2a2a2a !important;
            color: white !important;
            border: 1px solid #444 !important;
            border-radius: 4px !important;
            padding: 8px !important;
            margin: 5px 0 !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }
        
        /* Table styling */
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
        
        /* Drawer panel for unsold products */
        .drawer-panel {
            position: fixed !important;
            right: -400px !important;
            top: 0 !important;
            width: 400px !important;
            height: 100vh !important;
            background-color: #1e1e1e !important;
            z-index: 1000 !important;
            transition: right 0.3s ease !important;
            box-shadow: -2px 0 10px rgba(0, 0, 0, 0.5) !important;
            padding: 20px !important;
            box-sizing: border-box !important;
            overflow-y: auto !important;
        }
        
        .drawer-panel.open {
            right: 0 !important;
        }
        
        .drawer-trigger {
            position: fixed !important;
            right: 20px !important;
            bottom: 20px !important;
            background-color: #00ff9d !important;
            color: #121212 !important;
            border-radius: 50% !important;
            width: 60px !important;
            height: 60px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            cursor: pointer !important;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3) !important;
            z-index: 999 !important;
        }
    `;
    document.head.appendChild(style);
    
    console.log('Permanent layout visibility fix applied');
    
    if (window.location.href.includes('ecommerce')) {
        console.log('Adding drawer panel for unsold products...');
        
        if (!document.querySelector('.drawer-panel')) {
            const drawerPanel = document.createElement('div');
            drawerPanel.className = 'drawer-panel';
            drawerPanel.innerHTML = `
                <h2 style="color: #00ff9d !important;">Gestion des Invendus</h2>
                <div class="close-drawer" style="position: absolute; top: 10px; right: 10px; cursor: pointer; font-size: 24px; color: #00ff9d;">×</div>
                <div class="unsold-products-list" style="margin-top: 20px;"></div>
                <div class="action-buttons" style="margin-top: 20px;">
                    <button class="recycle-btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 10px 15px; border-radius: 4px; margin-right: 10px;">Recycler</button>
                    <button class="order-btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 10px 15px; border-radius: 4px;">Commander</button>
                </div>
                <div class="shipping-options" style="margin-top: 20px; display: none;">
                    <h3 style="color: #00ff9d !important;">Options d'expédition</h3>
                    <select class="shipping-method" style="width: 100%; padding: 8px; background-color: #2a2a2a; color: white; border: 1px solid #444; border-radius: 4px; margin-bottom: 10px;">
                        <option value="standard">Standard (3-5 jours)</option>
                        <option value="express">Express (1-2 jours)</option>
                        <option value="same-day">Même jour</option>
                    </select>
                    <button class="confirm-order-btn" style="background-color: #00ff9d; color: #121212; border: none; padding: 10px 15px; border-radius: 4px; width: 100%;">Confirmer la commande</button>
                </div>
            `;
            document.body.appendChild(drawerPanel);
            
            const drawerTrigger = document.createElement('div');
            drawerTrigger.className = 'drawer-trigger';
            drawerTrigger.innerHTML = '<span style="font-size: 24px;">+</span>';
            document.body.appendChild(drawerTrigger);
            
            drawerTrigger.addEventListener('click', function() {
                document.querySelector('.drawer-panel').classList.add('open');
            });
            
            document.querySelector('.close-drawer').addEventListener('click', function() {
                document.querySelector('.drawer-panel').classList.remove('open');
            });
            
            document.querySelector('.order-btn').addEventListener('click', function() {
                document.querySelector('.shipping-options').style.display = 'block';
            });
            
            document.querySelector('.confirm-order-btn').addEventListener('click', function() {
                const shippingMethod = document.querySelector('.shipping-method').value;
                alert('Commande confirmée avec expédition ' + shippingMethod + '. Vérification du solde de trésorerie en cours...');
            });
            
            const unsoldProductsList = document.querySelector('.unsold-products-list');
            const exampleProducts = [
                { name: 'Produit A', quantity: 5, price: '120€' },
                { name: 'Produit B', quantity: 3, price: '85€' },
                { name: 'Produit C', quantity: 8, price: '210€' }
            ];
            
            exampleProducts.forEach(product => {
                const productItem = document.createElement('div');
                productItem.style.padding = '10px';
                productItem.style.borderBottom = '1px solid #333';
                productItem.style.marginBottom = '10px';
                productItem.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <input type="checkbox" style="width: auto; margin-right: 10px;">
                            <span>${product.name}</span>
                        </div>
                        <div>
                            <span>${product.quantity} unités</span>
                            <span style="margin-left: 10px;">${product.price}</span>
                        </div>
                    </div>
                `;
                unsoldProductsList.appendChild(productItem);
            });
        }
        
        console.log('Drawer panel for unsold products added');
    }
    
    if (window.location.href.includes('parametres')) {
        console.log('Checking for API key fields...');
        
        const apiKeyFields = document.querySelectorAll('input[type="password"]');
        const apiKeyLabels = document.querySelectorAll('label');
        let hasAllApiKeys = false;
        
        const requiredApiKeys = [
            'Twelve Data', 'Alpha Vantage', 'Binance', 'Coinbase',
            'FRED', 'Kraken', 'NewsAPI', 'Shopify'
        ];
        
        let foundApiKeys = [];
        apiKeyLabels.forEach(label => {
            requiredApiKeys.forEach(key => {
                if (label.textContent.includes(key)) {
                    foundApiKeys.push(key);
                }
            });
        });
        
        hasAllApiKeys = requiredApiKeys.every(key => foundApiKeys.includes(key));
        
        if (!hasAllApiKeys) {
            console.log('Adding missing API key fields...');
            
            const apiKeySection = document.querySelector('form') || document.querySelector('section') || document.querySelector('main');
            
            if (apiKeySection) {
                const apiKeysContainer = document.createElement('div');
                apiKeysContainer.className = 'api-keys-container';
                apiKeysContainer.style.marginTop = '20px';
                
                const heading = document.createElement('h3');
                heading.textContent = 'Clés API';
                heading.style.color = '#00ff9d';
                apiKeysContainer.appendChild(heading);
                
                requiredApiKeys.forEach(key => {
                    if (!foundApiKeys.includes(key)) {
                        const apiKeyGroup = document.createElement('div');
                        apiKeyGroup.style.marginBottom = '15px';
                        
                        const label = document.createElement('label');
                        label.textContent = `${key} API Key`;
                        label.style.display = 'block';
                        label.style.marginBottom = '5px';
                        apiKeyGroup.appendChild(label);
                        
                        const inputGroup = document.createElement('div');
                        inputGroup.style.display = 'flex';
                        inputGroup.style.position = 'relative';
                        
                        const input = document.createElement('input');
                        input.type = 'password';
                        input.placeholder = `Entrez votre clé ${key}`;
                        input.style.flex = '1';
                        input.style.padding = '8px';
                        input.style.backgroundColor = '#2a2a2a';
                        input.style.color = 'white';
                        input.style.border = '1px solid #444';
                        input.style.borderRadius = '4px';
                        inputGroup.appendChild(input);
                        
                        const toggleButton = document.createElement('button');
                        toggleButton.type = 'button';
                        toggleButton.innerHTML = '<i class="fa fa-eye"></i>';
                        toggleButton.style.position = 'absolute';
                        toggleButton.style.right = '5px';
                        toggleButton.style.top = '50%';
                        toggleButton.style.transform = 'translateY(-50%)';
                        toggleButton.style.backgroundColor = 'transparent';
                        toggleButton.style.border = 'none';
                        toggleButton.style.color = '#00ff9d';
                        toggleButton.style.cursor = 'pointer';
                        toggleButton.addEventListener('click', function() {
                            if (input.type === 'password') {
                                input.type = 'text';
                                toggleButton.innerHTML = '<i class="fa fa-eye-slash"></i>';
                            } else {
                                input.type = 'password';
                                toggleButton.innerHTML = '<i class="fa fa-eye"></i>';
                            }
                        });
                        inputGroup.appendChild(toggleButton);
                        
                        apiKeyGroup.appendChild(inputGroup);
                        apiKeysContainer.appendChild(apiKeyGroup);
                    }
                });
                
                const saveButton = document.createElement('button');
                saveButton.textContent = 'Enregistrer les clés API';
                saveButton.style.backgroundColor = '#00ff9d';
                saveButton.style.color = '#121212';
                saveButton.style.border = 'none';
                saveButton.style.padding = '10px 15px';
                saveButton.style.borderRadius = '4px';
                saveButton.style.marginTop = '15px';
                saveButton.style.cursor = 'pointer';
                
                saveButton.addEventListener('click', function(e) {
                    e.preventDefault();
                    alert('Clés API enregistrées. Démarrage du backtesting automatique...');
                });
                
                apiKeysContainer.appendChild(saveButton);
                
                apiKeySection.appendChild(apiKeysContainer);
                
                console.log('Missing API key fields added');
            }
        }
    }
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
    
    console.log('Delayed layout fix completed');
}, 1000);
