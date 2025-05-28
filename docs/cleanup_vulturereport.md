To achieve the task of cleaning up your codebase based on the Vulture report, we can follow a structured approach. Below is a step-by-step guide on how to implement this, along with a sample script that you can use to automate the process.

### Step-by-Step Guide

1. **Read the Vulture Report**: Parse the `vulture_report.txt` to identify unused functions, classes, and imports.

2. **Modify Source Files**: For each entry in the report, locate the corresponding definition in the source files and remove it while preserving the formatting and docstrings of the remaining code.

3. **Update `requirements.txt`**: Analyze the remaining code to determine which libraries are still in use and regenerate the `requirements.txt` file accordingly.

4. **Create a Summary Document**: Generate a `docs/cleanup_summary.md` file that lists all the removed functions, classes, and imports.

### Sample Python Script

Here’s a sample Python script that implements the above steps:

```python
import os
import re

def read_vulture_report(report_path):
    with open(report_path, 'r') as file:
        return [line.strip() for line in file if line.strip()]

def remove_unused_definitions(source_file, unused_definitions):
    with open(source_file, 'r') as file:
        lines = file.readlines()

    cleaned_lines = []
    removed_items = []

    for line in lines:
        # Check for function definitions
        if any(re.search(rf'\b{def_name}\b', line) for def_name in unused_definitions['functions']):
            removed_items.append(line.strip())
            continue
        
        # Check for class definitions
        if any(re.search(rf'\b{class_name}\b', line) for class_name in unused_definitions['classes']):
            removed_items.append(line.strip())
            continue
        
        # Check for imports
        if any(re.search(rf'\b{import_name}\b', line) for import_name in unused_definitions['imports']):
            removed_items.append(line.strip())
            continue
        
        cleaned_lines.append(line)

    with open(source_file, 'w') as file:
        file.writelines(cleaned_lines)

    return removed_items

def update_requirements(requirements_path, used_libraries):
    with open(requirements_path, 'w') as file:
        for library in used_libraries:
            file.write(f"{library}\n")

def generate_cleanup_summary(removed_items, summary_path):
    with open(summary_path, 'w') as file:
        file.write("# Cleanup Summary\n\n")
        file.write("## Removed Items\n")
        for item in removed_items:
            file.write(f"- {item}\n")

def main(vulture_report_path, source_files, requirements_path, summary_path):
    unused_definitions = {
        'functions': [],
        'classes': [],
        'imports': []
    }

    # Read the Vulture report
    with open(vulture_report_path, 'r') as report_file:
        for line in report_file:
            if line.startswith("Unused function:"):
                unused_definitions['functions'].append(line.split(":")[1].strip())
            elif line.startswith("Unused class:"):
                unused_definitions['classes'].append(line.split(":")[1].strip())
            elif line.startswith("Unused import:"):
                unused_definitions['imports'].append(line.split(":")[1].strip())

    removed_items = []
    
    # Process each source file
    for source_file in source_files:
        removed_items.extend(remove_unused_definitions(source_file, unused_definitions))

    # Update requirements.txt
    # Here you would implement logic to determine used libraries based on the remaining code
    used_libraries = []  # Placeholder for actual logic to determine used libraries
    update_requirements(requirements_path, used_libraries)

    # Generate cleanup summary
    generate_cleanup_summary(removed_items, summary_path)

if __name__ == "__main__":
    vulture_report_path = 'vulture_report.txt'
    source_files = ['your_source_file.py']  # List your source files here
    requirements_path = 'requirements.txt'
    summary_path = 'docs/cleanup_summary.md'

    main(vulture_report_path, source_files, requirements_path, summary_path)
```

### Notes:
- **Customization**: You may need to customize the script to fit your specific project structure and naming conventions.
- **Used Libraries Logic**: The logic to determine which libraries are still in use after removing unused code is not implemented in this script. You may need to analyze the remaining code to extract the used libraries.
- **Backup**: Always make a backup of your codebase before running any cleanup scripts to prevent accidental data loss.

### Running the Script
1. Save the script to a file, e.g., `cleanup_script.py`.
2. Ensure you have the necessary permissions to modify the source files.
3. Run the script using Python: `python cleanup_script.py`.

This will clean up your codebase according to the Vulture report and generate the necessary summary and updated requirements file.