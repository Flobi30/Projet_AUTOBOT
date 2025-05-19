# Plan de refonte de l'interface utilisateur AUTOBOT

## Analyse des maquettes fournies

Les maquettes partagées montrent une interface avec les caractéristiques suivantes :
- Thème sombre avec fond noir (#121212)
- Éléments néon verts (#00ff9d) pour les accents et textes importants
- Disposition en grille avec cartes aux coins arrondis
- Icônes minimalistes pour les différentes sections
- Graphiques de performance avec courbes vertes sur fond noir
- Sections principales : Dashboard, Trading, E-commerce, Arbitrage, Backtest

## Pages HTML existantes

1. **simplified_dashboard.html** - Dashboard principal avec onglets
2. **arbitrage.html** - Page d'arbitrage avec graphiques et tableaux
3. **backtest.html** - Page de backtest avec formulaires et résultats
4. **mobile_dashboard.html** - Version mobile du dashboard
5. **deposit_withdrawal.html** - Page pour les dépôts et retraits
6. **ecommerce.html** - Page pour la gestion e-commerce

## Modifications nécessaires

### 1. Styles globaux (styles.css)

```css
:root {
    --bg-color: #121212;
    --card-bg-color: #1e1e1e;
    --text-color: #ffffff;
    --primary-color: #00ff9d;
    --secondary-color: #00cc7d;
    --accent-color: #00aa5d;
    --border-color: #333333;
    --success-color: #00ff9d;
    --warning-color: #ffcc00;
    --danger-color: #ff3333;
    --info-color: #00ccff;
}

body {
    background-color: var(--bg-color);
    color: var(--text-color);
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0;
    padding: 0;
}

.neon-text {
    color: var(--primary-color);
    text-shadow: 0 0 5px rgba(0, 255, 157, 0.5), 0 0 10px rgba(0, 255, 157, 0.3);
}

.card {
    background-color: var(--card-bg-color);
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    margin-bottom: 20px;
    border: 1px solid #333;
}
```

### 2. Modifications du Dashboard (simplified_dashboard.html)

- Remplacer le header par la version avec logo AUTOBOT et bouton Ghost Mode
- Ajouter les cartes Capital Total, Duplication, Performance
- Créer les boutons de navigation Trading, E-commerce, Arbitrage, Backtest avec icônes
- Ajouter la section Derniers logs avec messages système
- Intégrer le graphique de performance avec courbe verte

### 3. Page Capital (deposit_withdrawal.html)

- Renommer en "capital.html" pour correspondre aux maquettes
- Ajouter les sections Dépôt, Retrait, Seuil de retrait automatique
- Créer la section Capital Disponible avec messages système
- Ajouter la section Capital Social avec répartition Trading/Ecommerce/Arbitrage

### 4. Page Trading (trading.html)

- Créer cette page si elle n'existe pas
- Ajouter les sections Capital engagé total et Gains générés
- Intégrer le graphique de performance avec courbe verte
- Créer la section Historique des positions
- Ajouter la section Stratégies rentables avec gains par stratégie
- Intégrer les messages d'analyse de tendance

### 5. Intégration du Chat SuperAGI

- Ajouter un onglet "Chat" dans simplified_dashboard.html
- Créer l'interface de chat avec zone de saisie et historique des messages
- Connecter l'interface aux WebSockets pour la communication en temps réel

## Nouvelles pages à créer

1. **trading.html** - Page détaillée pour le trading
2. **capital.html** - Version améliorée de deposit_withdrawal.html
3. **performance.html** - Page dédiée aux métriques de performance

## Éléments visuels communs

- Logo AUTOBOT avec icône verte
- Bouton Ghost Mode dans le header
- Indicateurs de performance avec valeurs en vert
- Messages système avec préfixe [SYSTÈME]
- Graphiques avec courbes vertes sur fond noir
- Boutons avec effet néon au survol

## Plan d'implémentation

1. Modifier les fichiers CSS globaux pour appliquer le thème sombre et les couleurs néon
2. Mettre à jour simplified_dashboard.html pour correspondre à la maquette principale
3. Adapter les pages existantes (arbitrage.html, backtest.html) au nouveau style
4. Créer les nouvelles pages (trading.html, capital.html, performance.html)
5. Intégrer l'interface de chat pour SuperAGI
6. Tester la responsivité sur différentes tailles d'écran
7. Vérifier la cohérence visuelle entre toutes les pages
