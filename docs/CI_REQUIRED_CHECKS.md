# CI checks required before merge (critical branches)

For pull requests targeting critical branches (`main`, `master`, `work`), require the following status check in GitHub branch protection:

- `Required CI gates (critical branches)`

This gate depends on:

- `Conflict marker scan` (job id: `conflict-marker-scan` in `.github/workflows/security-and-audit.yml`).
- `Python lockfile integrity` (job id: `python-lockfiles`) to ensure `requirements.in -> requirements.txt` lock generation is reproducible and pinned.
- `Python dependency audit (pip-audit)` (job id: `python-audit`) on lockfiles `requirements/runtime.txt`, `requirements/api.txt`, and `requirements/tests.txt`.
- `Python tests (unit)` and `Python tests (integration)` from the `python-tests` matrix job.
- `Dashboard build and lint` (job id: `dashboard-build-lint`).

Recommended GitHub configuration:

1. Go to **Settings → Branches**.
2. Add (or edit) protection rules for `main`, `master`, `work`.
3. Enable **Require status checks to pass before merging**.
4. Mark `Required CI gates (critical branches)` as required.

Artifacts are published for diagnostics even when jobs fail.

## Single source of truth

To avoid drift between documentation and CI behavior:

1. Treat `.github/workflows/security-and-audit.yml` as the authoritative source for required gate wiring.
2. Keep `required-critical-gates.needs` synchronized with this document using exact job ids:
   - `conflict-marker-scan`
   - `python-lockfiles`
   - `python-audit`
   - `python-tests`
   - `dashboard-build-lint`
3. Keep the human-readable job name `Required CI gates (critical branches)` listed as the required status check in branch protection.
4. If a required job is moved to another workflow, create a dedicated aggregator in that target workflow and update this file in the same PR.

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

