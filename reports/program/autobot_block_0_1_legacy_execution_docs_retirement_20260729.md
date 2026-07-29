# AUTOBOT — Bloc 0.1 : retrait des guides d'execution legacy — 2026-07-29

## Decision

`GO_LOCAL_WAITING_FOR_VPS`.

Le runtime Compose et les controles d'execution etaient deja verrouilles en
observation-only. Cette passe retire l'ambiguite documentaire qui pouvait
encore faire croire qu'un lancement paper ou live etait une operation normale
du programme actuel.

## Changements

- `.env.example` impose desormais le verrou
  `AUTOBOT_OBSERVATION_ONLY_RUNTIME=true`, le mode paper desactive et tous les
  gardes d'execution/promotion/live a `false`; les placeholders de credentials
  Kraken prives et leur ancienne instruction d'usage ont ete retires.
- `README.md` decrit uniquement les references canoniques et les diagnostics
  research/shadow non autorisants.
- `docs/LIVE_PROMOTION_GATES.md` est archive et ne contient plus de procedure
  d'activation.
- Une regression statique interdit le retour de `PAPER_TRADING=true` dans les
  guides de premier niveau et exige les verrous observation-only du template.

## Verification

- Suite ciblee documentation/deploiement/frontiere d'execution : `21 passed`.
- Validateur README/template : `OK: 10 required vars documented and present`.
- Suite complete : `1989 passed, 6 skipped, 2 deselected`.
- `git diff --check` : passed.
- Aucun code de strategie, routeur, ordre, fill, secret, base runtime ou flag
  VPS n'a ete modifie.

## Limite

Ce changement ne declare aucune couche `VERIFIED` et ne rend aucune strategie
eligible. Une preuve VPS fraiche reste necessaire apres la maintenance Hetzner.
