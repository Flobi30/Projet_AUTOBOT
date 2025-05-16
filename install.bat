@echo off
echo 🤖 Installation d'AUTOBOT - Framework de Trading et RL 🤖
echo =========================================================

REM Vérifier si Python est installé
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python n'est pas installé. Veuillez installer Python 3.8+ depuis https://www.python.org/downloads/
    pause
    exit /b 1
) else (
    echo ✅ Python est déjà installé
)

REM Créer un environnement virtuel
echo 🔧 Création de l'environnement virtuel...
python -m venv venv
call venv\Scripts\activate.bat

REM Installer les dépendances
echo 📦 Installation des dépendances...
pip install -r requirements.txt

REM Configuration des clés API
echo 🔑 Configuration des clés API...
python installer.py --config-only

REM Lancer les backtests
echo 🧪 Lancement des backtests...
python run_backtests.py

echo ✅ Installation terminée avec succès!
echo 🚀 Pour lancer l'application, exécutez: python -m src.autobot.main
pause
