# prompts/cleanup_vulture.md

## System
You are GPT‑Code, an expert in Python refactoring and code cleanup.

## User
I have a report from Vulture listing unused functions, classes and imports.
Automatically remove **all** unused definitions from the codebase.
- For each entry in `vulture_report.txt`, delete the corresponding function/class/import.
- Preserve formatting and docstrings in the rest of the file.
- Do not touch code not listed in the report.
- Regenerate a cleaned `requirements.txt` with only the libraries still used.

## Output
- Modified source files with unused code removed.
- Updated `requirements.txt`.
- `docs/cleanup_summary.md` listing what was removed.
