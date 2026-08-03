# AUTOBOT Bloc 6 — capacité de sauvegarde SQLite chiffrée `age` (2026-08-04)

## Décision

`GO_CAPABILITY_DORMANT`.

AUTOBOT peut maintenant produire et vérifier une sauvegarde SQLite chiffrée
par clé publique `age`, sans charger ni stocker une identité privée dans le
code, Git, le conteneur ou le runtime. Aucun backup planifié n'est activé par
ce changement.

## Contrat ajouté

Deux commandes CLI explicitement opérateur sont disponibles :

```text
sqlite-backup-age
sqlite-backup-age-restore-drill
```

La création exige simultanément :

1. une clé publique `age1…` ;
2. un répertoire de staging existant, distinct de la destination ;
3. une destination inexistante ;
4. le binaire `age` explicite ;
5. un délai borné.

Le snapshot SQLite est d'abord contrôlé avec l'API de backup SQLite, puis
chiffré. Le manifest ne contient qu'un fingerprint de la clé publique, le hash
du snapshot clair et le hash du ciphertext. Une restauration exige le hash
clair attendu et une identité fournie de l'extérieur; l'identité, son chemin et
la sortie de `age` ne sont jamais imprimés dans le résultat.

## Garde-fous

- échec si `age` est absent, expire ou retourne une erreur ;
- échec si une destination existe déjà ;
- échec si le hash déchiffré ne correspond pas au manifest ;
- nettoyage des snapshots temporaires, y compris les sidecars SQLite ;
- vérification d'intégrité SQLite après déchiffrement ;
- aucune activation de backup automatique, de rétention ou de réplication
  off-VPS ;
- aucune dépendance avec une stratégie, une clé Kraken, le paper, le live ou
  l'exécution.

## Validation locale

```text
python -m py_compile \
  src/autobot/v2/research/resilience_readiness.py \
  src/autobot/v2/cli.py \
  tests/research/test_resilience_readiness.py \
  tests/test_v2_cli.py

python -m pytest \
  tests/research/test_resilience_readiness.py \
  tests/test_v2_cli.py -q
```

Résultat : `83 passed`.

Les tests couvrent le chiffrement/déchiffrement avec un runner hermétique,
l'absence de mutation de la source, le nettoyage du staging, le refus d'une
clé invalide, l'absence du binaire, les erreurs du binaire et le contrat CLI.

## Limites assumées

La politique de rétention, le stockage hors VPS et la conservation de
l'identité privée restent délibérément externes à AUTOBOT. Cette capacité ne
doit être activée qu'après choix d'un destinataire `age` public, d'un staging
protégé et d'une destination de sauvegarde approuvée. Elle ne constitue pas
une autorisation de paper, live ou exécution.
