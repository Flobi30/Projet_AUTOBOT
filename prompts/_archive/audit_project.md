# prompts/audit_project.md

## System
You are a senior software architect and code auditor.

## User
1. Analyze all Python code under src/ for:
   - Dead/unused functions, imports, variables.
   - Complexity hotspots (functions > 20 lines or nested loops).
   - Dependency bloat (unused requirements).
2. Produce a report:
   - List of items to remove or refactor.
   - Suggestions to improve project structure (folder layout, naming).
   - A cleaned‑up version of `requirements.txt`.
3. Output:
   - `docs/audit_report.md`
   - Updated `requirements.txt`
