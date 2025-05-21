#!/usr/bin/env python3
"""
Script pour sécuriser les templates Jinja2 en ajoutant des filtres default
aux variables qui n'en ont pas déjà.
"""
import os
import re
import sys

def secure_template(file_path):
    """Ajoute des filtres default aux variables Jinja2 qui n'en ont pas."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = r'{{(\s*)([a-zA-Z0-9_\.]+)(\s*)}}'
    
    def add_default_filter(match):
        spaces_before = match.group(1)
        var_name = match.group(2)
        spaces_after = match.group(3)
        
        if '|' in var_name:
            return '{{' + spaces_before + var_name + spaces_after + '}}'
        
        return '{{' + spaces_before + var_name + '|default("") ' + spaces_after + '}}'
    
    modified_content = re.sub(pattern, add_default_filter, content)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(modified_content)
    
    return content != modified_content  # Retourne True si des modifications ont été faites

def main():
    """Fonction principale."""
    templates_dir = os.path.join('src', 'autobot', 'ui', 'templates')
    
    if not os.path.exists(templates_dir):
        print(f"Répertoire {templates_dir} introuvable.")
        sys.exit(1)
    
    modified_files = 0
    total_files = 0
    
    for root, _, files in os.walk(templates_dir):
        for file in files:
            if file.endswith('.html'):
                file_path = os.path.join(root, file)
                total_files += 1
                
                if secure_template(file_path):
                    modified_files += 1
                    print(f"Sécurisé: {file_path}")
    
    print(f"\nTraitement terminé: {modified_files}/{total_files} fichiers modifiés.")

if __name__ == "__main__":
    main()
