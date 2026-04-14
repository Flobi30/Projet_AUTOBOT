# SECURITY

## Règles non-négociables
- Ne jamais committer de secret.
- Activer GitHub Secret Scanning + Push Protection.
- Workflow CI `security-and-audit.yml` requis avant merge.

## Incident secret leak
1. Révocation/rotation externe immédiate.
2. Créer `data/compromised_secret.marker` pour bloquer promotion/startup.
3. Remédiation complète (voir `reports/SECRET_COMPROMISE_REMEDIATION.md`).
4. Lever le blocage uniquement après preuve de rotation + `LEAKED_SSH_KEY_ROTATED_ACK=true`.
