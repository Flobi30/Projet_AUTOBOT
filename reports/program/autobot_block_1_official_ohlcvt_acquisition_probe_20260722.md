# AUTOBOT — Bloc 1 — Probe d'acquisition OHLCVT officielle — 2026-07-22

## Décision

`WAITING_FOR_DATA_SOURCE`.

La collecte REST publique Kraken est correctement isolée et fonctionnelle, mais
elle ne fournit pas une profondeur d'historique suffisante pour valider ou
relancer une stratégie intraday. L'archive OHLCVT officielle de Kraken est la
source appropriée pour un backfill long, mais son hébergeur renvoie une limite
de quota temporaire au moment de ce contrôle. AUTOBOT ne contourne pas cette
limite et n'utilise aucune donnée partielle comme preuve d'un nouvel edge.

## Périmètre et sécurité

- Commit de référence : `d570394e740e041dbc0d8f9c41f684660f5db7ff`.
- Requête REST : données publiques Kraken uniquement, sans clé ni endpoint
  privé.
- Probe réalisée dans un conteneur jetable : filesystem racine en lecture
  seule, `/tmp` éphémère, capacités Linux retirées, `no-new-privileges`, aucun
  montage de l'état runtime, du ledger, des secrets ou des données du projet.
- Aucune stratégie, promotion, exécution paper/live, sizing, levier, routeur ou
  ordre n'a été activé ou appelé.

## Résultat du probe REST borné

Requête : `BTCZEUR, ETHZEUR` × `5m, 1h`, période demandée
`2026-01-22T00:00:00Z → 2026-07-22T00:00:00Z`, au plus trois pages.

| Symbole | Horizon | Lignes fermées | Période effectivement fournie |
| --- | ---: | ---: | --- |
| BTCZEUR | 5m | 516 | 2026-07-20 05:05 → 2026-07-22 00:00 UTC |
| BTCZEUR | 1h | 704 | 2026-06-22 17:00 → 2026-07-22 00:00 UTC |
| ETHZEUR | 5m | 516 | 2026-07-20 05:05 → 2026-07-22 00:00 UTC |
| ETHZEUR | 1h | 704 | 2026-06-22 17:00 → 2026-07-22 00:00 UTC |

Le résultat confirme la limite documentée du endpoint OHLC public : le curseur
retourne les entrées les plus récentes plutôt que les six mois demandés. Les
fichiers temporaires, leur manifest et leur rapport ont été détruits avec le
conteneur ; ils ne sont pas devenus un dataset AUTOBOT.

## Source officielle d'archive

La documentation officielle Kraken indique une archive CSV OHLCVT complète et
des mises à jour trimestrielles. L'archive complète visible le 2026-07-22 est
`Kraken_OHLCVT.zip` (7 885 068 519 octets, soit environ 7,3 Gio). L'archive
trimestrielle `Kraken_OHLCVT_Q1_2026.zip` est visible (545 431 093 octets).

Source de provenance :
https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data

## Blocage observé

Les demandes de téléchargement officielles ont été validées jusqu'à la page de
confirmation de Google Drive, puis ont renvoyé `Quota exceeded` sans transférer
l'archive. Ce résultat a été constaté pour l'archive complète et pour celle du
T1 2026.

- aucun fichier ZIP incomplet ou HTML de substitution n'a été conservé ;
- aucune méthode de contournement du quota, compte tiers ou source non
  officielle n'a été utilisée ;
- le téléchargement sera retenté seulement après la fenêtre indiquée par
  l'hébergeur, avec un contrôle de taille et `unzip -tqq` avant import.

## Effet sur les gates de recherche

- Les historiques OHLCV canoniques runtime restent insuffisants pour les gates
  intraday à six mois.
- Les stratégies déjà rejetées restent rejetées : aucune n'est relancée sur
  une fenêtre récente incomplète.
- Les archives historiques, lorsqu'elles seront importées, resteront
  `research-only` et `HISTORICAL_ARCHIVE_NOT_RUNTIME_PARITY` jusqu'à preuve
  indépendante de parité runtime/shadow.
- `funding_basis` et les autres candidats existants ne gagnent aucune
  autorisation de retry, shadow, paper ou live par ce probe.

## Suite contrôlée

1. Retenter l'accès officiel après expiration du quota, sans boucle agressive.
2. Vérifier taille, intégrité ZIP, membres explicitement demandés et mapping
   de symboles avant lecture.
3. Importer initialement un sous-ensemble borné BTC/ETH, séparé du runtime,
   avec le CLI `import-kraken-ohlcvt-archive`.
4. Construire un snapshot canonique historique avec provenance, gaps et
   temporalité explicites.
5. Ne considérer une nouvelle expérience que si ce snapshot représente un
   changement matériel de données et que le registre de trials l'accepte.

## Validation documentaire

- `git diff --check` : requis avant commit.
- Aucun module Python n'est modifié par ce rapport ; aucun test de logique n'a
  besoin d'être élargi.
- La synchronisation GitHub/VPS/container reste à réaliser avec le commit qui
  versionnera ce constat.
