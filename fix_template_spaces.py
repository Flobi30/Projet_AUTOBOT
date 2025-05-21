#!/usr/bin/env python3
"""
Script pour corriger les espaces supplémentaires dans les filtres default
des templates Jinja2.
"""
import os
import re
import sys

def fix_template_spaces(file_path):
    """Corrige les espaces supplémentaires dans les filtres default."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = r'\{\{(\s*)([a-zA-Z0-9_\.]+)\|default\(""\)(\s+)\}\}'
    
    def fix_spaces(match):
        spaces_before = match.group(1)
        var_name = match.group(2)
        spaces_after = match.group(3)
        
        return '{{' + spaces_before + var_name + '|default("") }}'
    
    modified_content = re.sub(pattern, fix_spaces, content)
    
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
                
                if fix_template_spaces(file_path):
                    modified_files += 1
                    print(f"Corrigé: {file_path}")
    
    print(f"\nTraitement terminé: {modified_files}/{total_files} fichiers modifiés.")

if __name__ == "__main__":
    main()
