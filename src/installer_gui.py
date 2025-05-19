"""
AUTOBOT Windows Installer GUI

Ce module fournit l'interface graphique pour l'installateur Windows d'AUTOBOT.
Il affiche une fenêtre avec une barre de progression et des messages de statut
pour guider l'utilisateur à travers le processus d'installation.
"""

import tkinter as tk
from tkinter import ttk
import webbrowser
import os
from pathlib import Path

class InstallerGUI:
    """Interface graphique pour l'installateur AUTOBOT."""
    
    def __init__(self, root):
        """
        Initialise l'interface graphique.
        
        Args:
            root: Fenêtre racine Tkinter
        """
        self.root = root
        self.root.title("AUTOBOT Installer")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - 600) // 2
        y = (screen_height - 400) // 2
        self.root.geometry(f"600x400+{x}+{y}")
        
        if os.path.exists("resources/autobot_logo.ico"):
            self.root.iconbitmap("resources/autobot_logo.ico")
        
        try:
            self.banner_img = tk.PhotoImage(file="resources/autobot_banner.png")
            self.banner = tk.Label(self.root, image=self.banner_img)
            self.banner.pack(pady=20)
        except:
            self.title_banner = tk.Label(self.root, text="AUTOBOT", font=("Arial", 24, "bold"))
            self.title_banner.pack(pady=20)
        
        self.title = tk.Label(self.root, text="Installation d'AUTOBOT", font=("Arial", 16, "bold"))
        self.title.pack(pady=10)
        
        self.status_var = tk.StringVar()
        self.status_var.set("Préparation de l'installation...")
        self.status = tk.Label(self.root, textvariable=self.status_var, font=("Arial", 10))
        self.status.pack(pady=10)
        
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=20)
        
        self.final_frame = tk.Frame(self.root)
        self.final_message = tk.Label(self.final_frame, text="", font=("Arial", 10), justify=tk.LEFT, wraplength=500)
        self.open_browser_btn = tk.Button(self.final_frame, text="Ouvrir l'interface web", command=self.open_browser)
        self.exit_btn = tk.Button(self.final_frame, text="Fermer l'installateur", command=self.root.destroy)
        
        self.server_url = None
    
    def update_status(self, message):
        """
        Met à jour le message de statut.
        
        Args:
            message: Nouveau message à afficher
        """
        self.status_var.set(message)
        self.root.update()
    
    def update_progress(self, value):
        """
        Met à jour la barre de progression.
        
        Args:
            value: Valeur de progression (0-100)
        """
        self.progress["value"] = value
        self.root.update()
    
    def installation_complete(self, server_url, admin_password):
        """
        Affiche le message de fin d'installation.
        
        Args:
            server_url: URL du serveur AUTOBOT
            admin_password: Mot de passe administrateur généré
        """
        self.server_url = server_url
        
        self.final_message.config(text=f"""
Installation terminée avec succès !

AUTOBOT est maintenant installé et prêt à être utilisé.

Accédez à l'interface web pour configurer vos clés API :
{server_url}

Nom d'utilisateur : admin
Mot de passe : {admin_password}

Cliquez sur le bouton ci-dessous pour ouvrir l'interface web.
        """)
        
        self.final_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.final_message.pack(pady=10)
        self.open_browser_btn.pack(pady=5)
        self.exit_btn.pack(pady=5)
        
        self.status.pack_forget()
        self.progress.pack_forget()
        
        self.open_browser()
    
    def open_browser(self):
        """Ouvre le navigateur sur l'interface web d'AUTOBOT."""
        if self.server_url:
            webbrowser.open(self.server_url)
