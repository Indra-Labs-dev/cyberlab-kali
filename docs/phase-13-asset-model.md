# Phase 13 — Asset Model

## Objectif

Faire évoluer `Target` (Phase 11) vers un véritable modèle `Asset`, capable de représenter plus que des cibles de scan (hôtes, domaines, sous-domaines, URLs, services, containers, ressources de lab), sans casser l'existant : migration additive, zéro régression sur les APIs/tests/UI de la Phase 11.

## Écart constaté entre la roadmap fournie et l'état réel du repo

Avant implémentation, l'audit a confirmé que l'état décrit par la roadmap correspondait à la réalité du code (`Target` avec `target_type`/`authorization_status`, un seul point d'application de l'autorisation dans `POST /api/jobs`, Tool Registry à 31 outils, etc.) — aucune divergence significative trouvée entre la roadmap et le repo pour les Phases 1–12. Un document `docs/roadmap.md` (non suivi par git, probablement issu d'une session antérieure) contenait déjà une révision de cette même roadmap arrivant à des conclusions cohérentes ; il a été utilisé comme référence croisée mais chaque affirmation a été revérifiée contre le code réel plutôt qu'acceptée telle quelle.

## Décision architecturale : renommage + généralisation, pas une table parallèle

Deux approches étaient possibles :

1. **Table `assets` séparée**, synchronisée ou référencée depuis `targets`.
2. **`Target` devient littéralement un cas particulier d'`Asset`** : la table `targets` est renommée `assets` et étendue, `Target` devient un alias Python de `Asset`.

L'option 1 aurait créé deux sources de vérité à garder synchronisées — exactement le genre de duplication que la roadmap interdit explicitement (« ne pas créer un chemin d'exécution parallèle », « ne pas dupliquer inutilement »). L'option 2 a été retenue : une seule table, un seul modèle SQLAlchemy (`Asset`), et `Target`/`TargetType`/`AuthorizationStatus` sont des alias Python purs (`app/models/target.py`) vers `app/models/asset.py`. Toute route, tout test, tout code Phase 11 qui importe `from app.models.target import Target` continue de fonctionner à l'identique — `Target` *est* `Asset`, pas une classe séparée qui lui ressemble.

## Modèle

`Asset` (`backend/app/models/asset.py`, table `assets`) :

| Champ | Type | Notes |
|---|---|---|
| `type` | `AssetType` enum | `HOST`/`IP`/`DOMAIN`/`SUBDOMAIN`/`URL`/`SERVICE`/`CONTAINER`/`LAB`/`LAB_RESOURCE`/`OTHER`. `LAB` conservé (valeur historique Phase 11), `LAB_RESOURCE` ajouté (nom demandé par la roadmap pour les ressources de lab). Pas de `Cloud Resource`/`Database`/`Workstation` — aucun mécanisme de découverte associé n'existe, conformément à la roadmap (« un type sans découverte associée n'est qu'un menu déroulant vide »). |
| `criticality` | `AssetCriticality` enum | `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`, défaut `MEDIUM`. Saisie manuelle uniquement — aucun calcul automatique tant que le Risk Score (Phase 15) n'existe pas. |
| `authorization_status` | `AuthorizationStatus` enum | Inchangé depuis la Phase 11 (`LAB`/`AUTHORIZED`/`LOCAL`/`UNKNOWN`), même frontière de sécurité, même point d'application. |
| `tags` | `list[str]` (JSON) | Éditable via l'API, libre. |
| `technologies` | `list[str]` (JSON) | **Jamais éditable directement** — alimenté automatiquement par `app/assets/activity.py` à partir des plugins détectés par whatweb. |
| `first_seen` / `last_seen` | `datetime \| None` | **Jamais éditables directement** — dérivés de l'activité réelle des Jobs liés à l'asset (`target_id`), `NULL` tant qu'aucun job n'a été exécuté. |
| `asset_metadata` | `dict` (JSON) | Anciennement `target_metadata`. |

`Target` (`backend/app/models/target.py`) : `Target = Asset`, `TargetType = AssetType`, `AuthorizationStatus` réexporté. Deux propriétés de compatibilité sur `Asset` (`target_type`, `target_metadata`) font le pont avec les noms de champs Phase 11 pour que les schémas Pydantic Phase 11 (`TargetResponse`, qui lit `target.target_type`/`target.target_metadata` via `from_attributes`) continuent de fonctionner sans aucune modification.

## Migration (`392e4638a4d8_generalize_target_into_asset_model.py`)

Additive au sens « aucune donnée perdue, aucun contrat d'API cassé », mais implique un renommage (pas seulement des `CREATE TABLE`) :

1. `ALTER TABLE targets RENAME TO assets` — Postgres met à jour la contrainte `jobs.target_id → assets.id` automatiquement, aucune action requise côté `jobs`.
2. `ALTER TABLE assets RENAME COLUMN target_type TO type`, `RENAME COLUMN target_metadata TO asset_metadata`.
3. `ALTER TYPE target_type RENAME TO asset_type`, puis ajout des nouvelles valeurs (`SUBDOMAIN`, `SERVICE`, `LAB_RESOURCE`) via un bloc autocommit (`ALTER TYPE ... ADD VALUE` ne peut pas s'exécuter dans la même transaction qu'une utilisation de la nouvelle valeur).
4. Ajout des colonnes `criticality` (défaut `MEDIUM`), `tags`/`technologies` (JSON, défaut `[]`), `first_seen`/`last_seen` (nullable, non backfillées depuis `created_at` — seulement depuis l'historique réel des jobs, cf. ci-dessous).
5. Backfill `first_seen`/`last_seen` par une requête `UPDATE ... FROM (SELECT target_id, MIN(created_at), MAX(COALESCE(finished_at, created_at)) FROM jobs GROUP BY target_id)` — un asset jamais scanné reste `NULL`/`NULL`, ce qui est l'état honnête plutôt que de mentir avec `created_at`.

`downgrade()` inverse les renommages et supprime les colonnes ajoutées ; les valeurs d'enum ajoutées par `ADD VALUE` ne peuvent pas être retirées proprement par Postgres et restent inutilisées après un downgrade — limitation documentée, pas un oubli.

**Vérifié réellement** : backup de la base dev (`pg_dump`) pris avant migration, `alembic upgrade head` exécuté contre le vrai Postgres du stack Docker, schéma résultant inspecté via `psql` (`\d assets`, `enum_range`), FK confirmée pointer vers `assets`.

## API

- **`/api/targets`, `/api/projects/{id}/targets` : strictement inchangés.** Mêmes routes, même schéma de réponse (`target_type`, `target_metadata`), mêmes tests Phase 11 verts sans modification.
- **Nouveau : `/api/assets`** (`backend/app/api/routes/assets.py`) — `GET` (filtres `project_id`/`type`/`criticality`/`authorization_status`/`search`), `GET /{id}`, `PATCH /{id}`, `DELETE /{id}`, `GET /{id}/jobs`. `POST /api/projects/{id}/assets` (création, dans `projects.py` à côté de la route `targets` existante).
- `AssetUpdateRequest` n'expose délibérément pas `first_seen`/`last_seen`/`technologies` — un `PATCH` qui tente de les fixer est silencieusement ignoré (champ absent du schéma), pas une erreur 422 : ces champs ne sont modifiables que par l'activité réelle.
- Une ressource créée via `/api/projects/{id}/targets` est immédiatement visible via `/api/assets/{id}` et vice versa (même ligne) — vérifié par test et manuellement.

## Activité dérivée (`backend/app/assets/activity.py`)

`record_asset_activity()` est appelée depuis `execute_job()` (`backend/app/jobs/tasks.py`) une fois qu'un job lié à un `target_id` atteint un état terminal (`SUCCESS` ou `FAILED` — le scan a réellement eu lieu dans les deux cas) :

- `first_seen` fixé à la première observation, jamais reculé ensuite.
- `last_seen` avancé à chaque nouvelle observation.
- Pour `whatweb` en `SUCCESS`, `technologies_from_whatweb()` extrait les noms de plugins détectés (même logique que `extract_from_whatweb` dans `app/findings/extractor.py`) et les fusionne (union, sans doublons) dans `Asset.technologies`.

## Vérification end-to-end réelle (pas seulement des tests unitaires)

Exécuté contre le stack Docker complet (Postgres réel, worker RQ réel, conteneur Kali réel, lab DVWA réel) :

1. Backup de la base dev, migration appliquée, schéma vérifié via `psql`.
2. Rebuild + redémarrage de `cyberlab-api`/`cyberlab-worker`/`cyberlab-frontend`.
3. Création d'un projet et d'un asset `CONTAINER` (`cyberlab-kali`) via l'API réelle (authentifiée, `AUTH_ENABLED=true`) — `criticality: HIGH`, `tags` fournis, autorisation `LAB` auto-détectée.
4. Job `nmap` réel lancé via `target_id` → `SUCCESS` → `first_seen`/`last_seen` peuplés avec l'horodatage réel du job.
5. Lab DVWA démarré réellement, asset `LAB_RESOURCE` créé (nouvelle valeur d'enum Phase 13) avec autorisation `LAB` auto-détectée depuis le hostname du lab.
6. Job `whatweb` réel lancé deux fois contre DVWA → `technologies` peuplé (`Apache`, `DVWA`, `PHP`, ...) après le premier run, `last_seen` avancé sans reculer `first_seen` au second run.
7. UI réelle (navigateur, `http://localhost:3300/targets`) : liste des assets avec les nouvelles colonnes (type/criticality/last seen), page de détail avec sélecteurs criticité/autorisation, ajout d'un tag en direct via un vrai clic + saisie clavier, persistance confirmée après rechargement.
8. Vue « Targets » de la page Project (legacy, toujours branchée sur `/api/projects/{id}/targets`) vérifiée sans régression, affiche les mêmes assets y compris le type `LAB_RESOURCE`.
9. Nettoyage : lab arrêté, assets/projet de test supprimés, logs `cyberlab-api`/`cyberlab-worker` vérifiés sans erreur.
10. Suite de tests complète (152 tests, dont 21 nouveaux) rejouée contre une base `_test` fraîchement recréée : verte.

## Frontend

`frontend/app/pages/targets/index.vue` et `.../targets/[id].vue` migrés pour consommer `/api/assets` (mêmes lignes que `/api/targets`, superset de champs) : filtres type/criticité/autorisation étendus, formulaire de création avec criticité + tags, page de détail avec sélecteur de criticité, gestion de tags (ajout/suppression), affichage des technologies détectées et de l'activité (first/last seen).

Portée volontairement limitée : la page `/projects/{id}` (onglet Targets) et les sélecteurs de cible dans `/ai` et `/tools` restent branchés sur `/api/targets` — ils continuent de fonctionner à l'identique (même données, même table) mais n'affichent pas encore les nouveaux champs Asset. Choix délibéré pour limiter la surface modifiée à ce qui est nécessaire pour cette phase ; ces pages pourront adopter les champs Asset dans une phase ultérieure si le besoin se confirme.

## Sécurité

- **Aucun changement au point d'application de l'autorisation.** `is_executable()`/`infer_default_authorization()` (`backend/app/targets/authorization.py`) n'ont pas été modifiés ; `POST /api/jobs` reste l'unique point d'application, désormais sur des lignes `Asset` plutôt que `Target`, mais avec la même sémantique.
- **`/api/assets` couvert par le même middleware d'authentification** que le reste de `/api/*` — vérifié explicitement (routes ajoutées à `test_every_api_route_is_guarded_when_auth_enabled`), pas seulement supposé parce que le middleware est un garde de préfixe de chemin.
- **`AssetUpdateRequest` empêche l'auto-assignation (mass assignment) de `first_seen`/`last_seen`/`technologies`** — absents du schéma, donc ignorés silencieusement plutôt que d'exposer un moyen de mentir sur l'historique d'activité réel.
- **Filtre `search` sur `Asset.name`** : `ilike()` lié par paramètre via SQLAlchemy (comme le faisait déjà `targets.py`), pas de concaténation de chaîne — pas d'injection SQL.
- **Aucun nouvel import dans `app/ai/`** : le test statique `test_ai_module_has_no_write_access_to_target_model` (qui interdit tout import du modèle Target/Asset dans `app/ai/*.py`) passe toujours — l'IA n'a acquis aucun accès supplémentaire au modèle Asset.
- **Frontend** : aucun `v-html`, tags/technologies/noms rendus via interpolation Vue échappée par défaut — pas de nouvelle surface XSS.

## Limites connues / hors scope de cette phase

- Pas de recalcul automatique de `criticality` (prévu Phase 15, Risk Score).
- Pas de détection de changement entre deux scans successifs (prévu Phase 14, Diff Engine) — `last_seen` avance, mais rien n'est encore fait avec la différence entre deux résultats.
- `technologies` n'est alimenté que par whatweb pour l'instant ; nuclei/autres outils pourraient enrichir ce champ dans une phase ultérieure.
- Le chemin `POST /api/jobs` avec `target` en texte libre (sans `target_id`) reste, comme documenté depuis la Phase 11, hors du système d'autorisation et donc hors du système d'activité Asset (`record_asset_activity` ne s'exécute que si `job.target_id` est renseigné) — comportement inchangé, pas une régression de cette phase.
