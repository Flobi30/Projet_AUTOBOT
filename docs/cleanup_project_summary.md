To perform the cleanup and refactoring of the AUTOBOT project as specified, follow these steps:

### Step 1: Scan the Project Directory

1. **Identify Dead/Unused Code**:
   - Use tools like `vulture` or `flake8` to find unused functions, classes, and imports.
   - Manually review the codebase for any empty or placeholder modules.

2. **Identify Unreferenced Test Files**:
   - Check for test files that do not correspond to any source files or are not executed in the test suite.

### Step 2: Remove Unused Code, Modules, and Imports

- Remove all identified dead code, unused imports, and empty modules.
- Ensure that the codebase still functions correctly after these removals.

### Step 3: Reorganize the Folder Structure

- Move all relevant files into the specified structure:
  ```
  src/
      data/
      broker/
      backtest/
      agents/
      ecommerce/
      monitoring/
      security/
      rl/
      stress_test/
  ```
- Remove any top-level Python files or folders that do not match the manifest.

### Step 4: Clean Up `requirements.txt`

- Analyze the codebase to determine which libraries are actually used.
- Remove any libraries from `requirements.txt` that are not utilized in the project.

### Step 5: Output the Results

1. **Modified Project Tree**:
   - Create a visual representation of the updated project structure, indicating files that were removed or moved.

2. **Summary Report**:
   - Create `docs/cleanup_project_summary.md` that lists every removal or move, detailing what was changed.

### Example of the Output

#### Modified Project Tree
```
AUTOBOT/
├── docs/
│   └── cleanup_project_summary.md
└── src/
    ├── data/
    ├── broker/
    ├── backtest/
    ├── agents/
    ├── ecommerce/
    ├── monitoring/
    ├── security/
    ├── rl/
    └── stress_test/
```

#### Summary Report (`docs/cleanup_project_summary.md`)
```markdown
# Cleanup Project Summary

## Removed Unused Code
- Removed unused functions and classes from:
  - `src/old_module.py`
  - `src/unused_file.py`
  
## Removed Empty Modules
- Deleted empty module:
  - `src/empty_module.py`

## Removed Unreferenced Test Files
- Deleted unreferenced test files:
  - `tests/test_unused.py`

## Reorganized Folder Structure
- Moved files to match the manifest:
  - `src/legacy_code.py` moved to `src/legacy/legacy_code.py`
  - `src/old_folder/` removed

## Cleaned Up requirements.txt
- Removed unused libraries:
  - `unused_library`
```

### Final Steps

- Ensure that all changes are committed to version control.
- Run tests to verify that the project is still functioning as expected after the cleanup.