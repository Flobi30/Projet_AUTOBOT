# Contributing

## Frontend canonical structure (mandatory)

The only canonical frontend source tree is:

- `dashboard/src/`

All React/TypeScript UI code must live under this tree, for example:

- `dashboard/src/pages/*`
- `dashboard/src/components/*`
- `dashboard/src/store/*`

### Forbidden frontend locations

Do **not** add React page/component files at repository root (e.g. `./MyPage.tsx`, `./Widget.jsx`).
Do **not** keep duplicate frontend pages outside `dashboard/src`.

### CI enforcement

CI runs `scripts/check_frontend_paths.sh` and fails if any `*.tsx` or `*.jsx` file appears at repository root.

Before opening a PR, run:

```bash
bash scripts/check_frontend_paths.sh
```
