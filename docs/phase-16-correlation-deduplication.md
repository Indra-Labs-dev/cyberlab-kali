# Phase 16 — Corrélation, Déduplication & Cycle de vie des Findings

## Objectif

Répondre à : *« Ce Finding, je l'ai déjà vu — c'est le même ou un nouveau ? »* et *« Ces deux Findings distincts sont-ils liés ? »*, plus un cycle de vie explicite (`NEW → CONFIRMED → ...`) pour suivre le traitement humain d'un Finding dans le temps — sans jamais dupliquer un Finding déjà connu ni fabriquer un lien non prouvé.

## Audit initial

Avant implémentation : chaque exécution de job créait un `Finding` inconditionnellement (`app/jobs/tasks.py::execute_job`, boucle `for finding_data in extract_findings(...): session.add(Finding(...))`) — un scan répété (manuel ou via le ticker Phase 14) produisait autant de lignes `findings` que d'exécutions, sans notion d'identité stable. Aucune table de relations entre Findings n'existait. `Finding` n'avait aucun champ de statut/cycle de vie.

## Architecture retenue — déduplication ≠ corrélation

Deux mécanismes strictement séparés :

- **Déduplication** : *fusionne* deux observations en une seule ligne `Finding` quand elles décrivent la **même chose** (`app/findings/signature.py` + `app/findings/service.py`).
- **Corrélation** : *lie* deux Findings **réellement distincts** via une ligne `finding_relations` explicite, quand une règle fixe détecte qu'ils sont probablement liés (`app/findings/correlation.py`) — jamais une fusion.

## Déduplication — signature à deux niveaux

`app/findings/signature.py::finding_signature()`, pure, déterministe, SHA-256 :

1. **Si le Finding porte un ou plusieurs CVE** : `(asset_id, CVE ids triés/majuscules)` — volontairement **indépendant de l'outil** : deux outils différents rapportant le même CVE sur le même asset fusionnent en un seul Finding.
2. **Sinon** : `(asset_id, titre normalisé, port, protocole)` — indépendant de l'outil en principe, mais chaque extracteur produit des titres suffisamment distincts en pratique pour que deux outils différents ne collisionnent jamais ici ; le rapprochement cross-outil pour ce cas passe par la corrélation, pas par la signature.

`source_tool` n'entre **jamais** dans la signature — c'est le rôle de `source_tools` (liste, voir plus bas) de tracer la provenance séparément de l'identité.

Un Finding dont le Job n'a pas de `target_id` (cible en texte libre, pas d'Asset) reçoit `signature = NULL` et reste **entièrement hors dédup/lifecycle/corrélation** — même précédent que le Diff Engine (Phase 14) et le Risk Score (Phase 15), qui ignorent déjà les jobs sans `target_id`.

Contrainte SQL : index unique partiel `uq_findings_signature` (`WHERE signature IS NOT NULL`) — décrit à la fois dans la migration Alembic et dans le modèle SQLAlchemy (`app/models/finding.py::Finding.__table_args__`), voir "Bug réel trouvé" plus bas pour pourquoi les deux sont nécessaires.

### `extract_port_protocol()` — dérivation du port

nmap/masscan exposent `port`/`protocol` directement dans `evidence`. Les autres outils dérivent le port du champ `target` du Finding via `urlparse` (préfixé `//` si aucun schéma n'est présent, pour que `urlparse` extraie correctement `host:port`/`host` sans schéma). **Bug réel trouvé pendant la vérification E2E** (voir plus bas) : les extracteurs whatweb/nuclei stockaient le `target` générique du Job (ex. `"cyberlab-lab-dvwa-c55eb6d4"`, sans schéma) au lieu de l'URL réellement scannée par résultat — `extract_port_protocol` ne pouvait donc jamais dériver de port pour ces deux outils, empêchant `RULE_NMAP_WHATWEB_PORT`/`RULE_NMAP_NUCLEI_PORT` de jamais matcher. Corrigé dans `app/findings/extractor.py` : `extract_from_whatweb`/`extract_from_nuclei` utilisent désormais l'URL résolue par résultat (`result["target"]`/`item["matched_at"]`), déjà disponible dans la sortie parsée mais jusque-là seulement utilisée dans la description texte.

## Fusion des observations — `app/findings/service.py::upsert_finding()`

Race-safe via PostgreSQL, pas un verrou applicatif : `SELECT ... FOR UPDATE` sur la ligne existante si la signature correspond, sinon INSERT spéculatif dans une SAVEPOINT (`session.begin_nested()`). Si l'INSERT échoue sur l'index unique (une autre session a créé la même signature entre-temps), la SAVEPOINT est annulée et la boucle retente (`SELECT ... FOR UPDATE` retrouve alors la ligne fraîchement commitée) — jusqu'à 5 tentatives. Preuve réelle : `tests/findings/test_concurrency.py`, deux vraies sessions Postgres/threads Python qui déposent la même signature simultanément, exactement 1 Finding en résultat, rejoué 5 fois consécutives sans échec.

Règles de fusion (`_merge_observation`) :

- `first_seen` ne recule jamais, `last_seen` n'avance que si l'observation est plus récente.
- `observation_count += 1` à chaque fusion.
- `source_tools`/`observation_job_ids` : union sans doublon, jamais de suppression.
- `cve_ids` : union.
- **Une valeur connue n'est jamais écrasée par une valeur inconnue** : `recommendation`/`description` ne changent que si la nouvelle observation en fournit une (`if new_value:`), sinon la valeur existante est conservée.
- `evidence` : la plus récente l'emporte (les preuves brutes des jobs contributeurs restent accessibles via `observation_job_ids`, jamais supprimées).
- Risk Score (Phase 15) recalculé uniquement si `cve_ids` a changé — jamais un recalcul systématique sans raison.

## Cycle de vie — `app/findings/lifecycle.py`

Dictionnaire Python fixe de transitions valides, pas un moteur de workflow générique :

```
NEW → CONFIRMED
CONFIRMED → IN_REVIEW
IN_REVIEW → ACCEPTED_RISK | FALSE_POSITIVE | REMEDIATED
ACCEPTED_RISK → REOPENED
FALSE_POSITIVE → REOPENED
REMEDIATED → REOPENED
REOPENED → CONFIRMED | IN_REVIEW
```

Toute transition (manuelle ou automatique) est journalisée dans `finding_status_history` (append-only). `maybe_auto_reopen()` est appelé à chaque fusion : rouvre automatiquement depuis `REMEDIATED`/`FALSE_POSITIVE` uniquement — **`ACCEPTED_RISK` ne rouvre jamais automatiquement** (décision humaine consciente, ne doit pas être silencieusement annulée par une re-détection), et aucun statut ne passe automatiquement à `CONFIRMED` (une simple re-observation ne vaut pas confirmation humaine).

Vérifié réellement contre le stack Docker (pas seulement en test unitaire) : `NEW → CONFIRMED → IN_REVIEW → FALSE_POSITIVE` (3 PATCH manuels) puis re-scan whatweb réel → `REOPENED` automatique avec l'historique complet ; séquence identique jusqu'à `ACCEPTED_RISK` puis re-scan nmap réel → statut inchangé, `observation_count` incrémenté.

## Corrélation — 3 règles fixes, pas de moteur générique

`app/findings/correlation.py`, scope : les Findings d'un seul Asset (celui du job qui vient de se terminer), jamais un passage global N×N.

- `RULE_NMAP_WHATWEB_PORT` / `RULE_NMAP_NUCLEI_PORT` : un port nmap `state=open` et un Finding whatweb/nuclei dont le port dérivé (`extract_port_protocol`) correspond.
- `RULE_SHARED_TECHNOLOGY` : le nom d'un plugin whatweb (≥ 3 caractères) apparaît en sous-chaîne dans le titre+description d'un Finding d'un autre outil.

Idempotence : ordre canonique des UUID (`sorted(...)`) pour que `(A,B)` et `(B,A)` soient toujours stockés de la même façon, contrainte unique `(finding_id, related_finding_id, rule)` — vérifié réellement (deux passages successifs de `correlate_asset_findings` sur les mêmes Findings, second passage : 0 relation créée).

## Risk Score — pas de réimplémentation

`upsert_finding()` appelle `app/risk/service.py::recalculate_finding_risk()` (Phase 15) tel quel, uniquement quand `cve_ids` change lors d'une fusion. La corrélation n'a aucun effet sur le Risk Score (les relations décrivent un lien entre Findings, pas une donnée d'entrée du calculateur).

## API

```
GET   /api/findings?...&status=&source_tool=          (filtres ajoutés)
GET   /api/findings/{id}/history                        historique de statut, plus récent en premier
GET   /api/findings/{id}/relations                       relations normalisées (finding_id = l'ID demandé, quel que soit l'ordre canonique stocké)
PATCH /api/findings/{id}/status  {status, reason?}       400 si transition invalide, jamais un statut arbitraire
```

Toutes protégées par le même middleware d'authentification que le reste de l'API (`test_every_api_route_is_guarded_when_auth_enabled` étendu aux 3 nouvelles routes).

## Frontend

Pages `/findings` et `/findings/[id]` étendues (pas de refonte) : filtres `status`/`source_tool`, badge de statut coloré, compteur d'observations sur la liste ; panneau Lifecycle (first_seen/last_seen/observation_count, source_tools, boutons de transition limités aux statuts valides via un miroir client de `VALID_TRANSITIONS`, historique) et panneau Related Findings (règle + raison lisible, lien vers le Finding lié) sur la page de détail. Le graphe de sécurité (visualisation) reste explicitement Phase 17 — ici uniquement une liste texte.

## Vérification end-to-end réelle

1. Asset créé (`DVWA E2E`) lié au lab DVWA réel (`cyberlab-lab-dvwa-c55eb6d4`, démarré via `POST /api/labs/{id}/start`).
2. `nmap`, `whatweb`, `nuclei` réels exécutés contre cet Asset via `POST /api/jobs`.
3. **Bug réel découvert et corrigé** (voir "Déduplication" ci-dessus) : premier passage, aucune relation créée malgré un port nmap ouvert et des Findings whatweb au bon endroit — cause trouvée (`Finding.target` générique, pas l'URL résolue), corrigée dans `extractor.py`, images `cyberlab-api`/`cyberlab-worker` reconstruites et redéployées, re-testé.
4. Après correction : `RULE_NMAP_WHATWEB_PORT` a produit 10 relations réelles (une par technologie whatweb détectée sur le port 80), vérifiées via `GET /api/findings/{id}/relations` et dans l'UI réelle (panneau "Related Findings").
5. Re-scan whatweb identique → 0 nouveau Finding, `observation_count` incrémenté sur les 10 Findings existants, 0 nouvelle relation (idempotence confirmée).
6. Cycle de vie complet testé en conditions réelles via l'UI (clic navigateur, pas un appel API direct) : `NEW → CONFIRMED` avec raison saisie, historique affiché correctement.
7. `FALSE_POSITIVE` puis re-scan réel → `REOPENED` automatique, historique complet (`triggered_by: automatic`), Risk Score toujours cohérent.
8. `ACCEPTED_RISK` puis re-scan réel → statut inchangé (pas de réouverture), `observation_count` incrémenté — règle métier critique vérifiée en conditions réelles, pas seulement en test unitaire.
9. `docker compose restart cyberlab-worker` exécuté au milieu de la séquence, puis nouveau re-scan whatweb : `observation_count` continue de s'incrémenter correctement, nombre de relations inchangé (10) — aucune duplication/perte/corruption après redémarrage.
10. Suite de tests complète (367 tests, dont 75 nouveaux pour cette phase) rejouée contre une base `_test` fraîchement recréée : verte.

## Bugs réels trouvés et corrigés pendant la vérification (REPRODUCE → DOCUMENT → FIX → TEST → RETEST)

- **`upsert_finding()` plantait pour tout Finding sans Asset** : `recalculate_finding_risk()` était appelé avant tout `flush()`, donc avant que la valeur par défaut de la colonne `confidence` soit matérialisée sur l'objet Python — `Confidence(None)` levait `ValueError`. Trouvé par un test écrit pour ce cas précis (`test_upsert_finding_without_asset_never_dedups`), pas par la vérification manuelle. Corrigé par un `session.flush()` explicite avant le recalcul.
- **L'index unique partiel `uq_findings_signature` n'existait que dans la migration Alembic, pas dans le modèle SQLAlchemy** : `Base.metadata.create_all()` (utilisé par `tests/conftest.py` pour construire la base de test) ne le créait donc jamais — le test de concurrence obtenait silencieusement **2 Findings** pour la même signature au lieu d'1, sans qu'aucune erreur ne remonte. Corrigé en déclarant le même index (même nom, même `WHERE`) directement sur `Finding.__table_args__` — la base réelle (déjà migrée) n'est pas affectée (`create_all()` ignore les tables déjà existantes), seule la base de test bénéficie désormais de la même garantie que la production.
- **`session.expunge()` sur une instance déjà détachée** : après un `IntegrityError` capturé dans la boucle de retry, la SAVEPOINT annulée détache déjà l'objet `finding` — l'appel explicite à `session.expunge(finding)` levait `InvalidRequestError`. Corrigé par une vérification `if finding in session` avant l'expunge.
- **Extraction du `target` whatweb/nuclei** : voir "Déduplication" ci-dessus — trouvé pendant la vérification E2E réelle (pas par les tests unitaires, qui construisaient déjà des Findings avec un `target` correctement résolu).

## Limites connues / hors scope

Explicitement **non traité** dans cette phase (voir aussi la section dédiée dans [security.md](security.md#phase-16--corrélation-déduplication--cycle-de-vie--audit-de-sécurité)) :

- **Security Graph** / visualisation de graphe — Phase 17. Ici uniquement une liste de relations textuelle.
- **Attack Path** — hors scope, nécessite le Security Graph.
- **Neo4j** ou toute base graphe — `finding_relations` est une table relationnelle PostgreSQL classique, suffisante pour 3 règles fixes.
- **Moteur de règles générique / DSL de corrélation** — 3 fonctions Python fixes, pas un système extensible par configuration.
- **Event Bus** — la corrélation est appelée en synchrone à la fin de `execute_job()`, pas via un bus d'événements.
- **SIEM** — hors scope produit.
- **Multi-worker / multi-Kali** — la garantie de concurrence repose sur PostgreSQL (vraie pour N workers), mais aucune infrastructure multi-worker n'est déployée ou testée ici.
- **Auto-remédiation** — `REMEDIATED` reste un statut déclaré manuellement par un humain, jamais déduit automatiquement.
- **Multi-tenant / RBAC** — cohérent avec le modèle mono-utilisateur déjà établi (Phase 11) ; `triggered_by` distingue *comment* une transition a eu lieu (manuel/automatique), jamais *qui*.
- **Pas de fabrication de relations historiques** : les Findings créés avant cette phase ne reçoivent ni signature (`NULL`, honnête plutôt que deviné) ni relation rétroactive — seules les nouvelles observations en bénéficient.
