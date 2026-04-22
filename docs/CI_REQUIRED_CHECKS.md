# CI checks required before merge (critical branches)

For pull requests targeting critical branches (`main`, `master`, `work`), require the following status check in GitHub branch protection:

- `Required CI gates (critical branches)`

This gate is the `required-critical-gates` job in `.github/workflows/security-and-audit.yml` and its `needs` list is:

1. `conflict-marker-scan`
2. `python-lockfiles`
3. `secret-scan`
4. `python-audit`
5. `python-tests`
6. `npm-audit`
7. `dashboard-build-lint`
8. `dashboard-build`
9. `leaked-secret-promotion-guard`

## Branch protection names to use (verified)

GitHub branch protection expects **displayed check names** (job `name`), not job ids.

Use exactly:

- `Required CI gates (critical branches)`

Verification against `.github/workflows/security-and-audit.yml`:

- Gate job id: `required-critical-gates`
- Gate displayed name: `Required CI gates (critical branches)`

These match what should appear in the branch protection status-check selector for this gate.

## Update policy (no drift)

Any change to `required-critical-gates.needs` in `.github/workflows/security-and-audit.yml` **must update this document in the same PR**.

Recommended GitHub configuration:

1. Go to **Settings → Branches**.
2. Add (or edit) protection rules for `main`, `master`, `work`.
3. Enable **Require status checks to pass before merging**.
4. Mark `Required CI gates (critical branches)` as required.

Artifacts are published for diagnostics even when jobs fail.

Additionally, enforce the dedicated pre-merge routine described in `docs/PRE_MERGE_ROUTINE.md`.

## Flux de mise à jour des dépendances secondaires (AUTOBOT V2)

Les fichiers `src/autobot/v2/api/requirements.txt` et `src/autobot/v2/tests/requirements.txt` **ne doivent plus contenir de contraintes flottantes**.
Ils référencent explicitement les lockfiles centraux:

- `src/autobot/v2/api/requirements.txt` → `requirements/api.txt`
- `src/autobot/v2/tests/requirements.txt` → `requirements/tests.txt`

Workflow recommandé pour éviter toute divergence de versions:

1. Modifier la source `.in` correspondante uniquement (`requirements/api.in`, `requirements/tests.in`, ou `requirements/runtime.in` selon le besoin).
2. Régénérer les lockfiles avec `pip-compile` (ou lancer le check automatisé ci-dessous).
3. Valider localement: `python tools/check_dependency_locks.py`.
4. Vérifier qu'aucun fichier secondaire sous `src/autobot/v2/**/requirements.txt` n'introduit une version ad hoc (pas de `>=`, `~=` ou version libre).
5. Committer ensemble: les `.in`, les `.txt` lockés, et la documentation impactée.

Ce flux impose une stratégie **mono-lock** pour les dépendances secondaires V2: la résolution des versions est centralisée dans `requirements/*.txt` et consommée par référence, ce qui aligne dev, CI et production.
