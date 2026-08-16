# SOC-lite — vue "Findings actifs + changements récents"

## Périmètre exact (override explicite)

Le texte de la roadmap (`docs/roadmap.md`, §8) définit SOC-lite ainsi : « pas une plateforme SOC complète... mais une vue "Findings actifs + changements récents" déjà largement couverte par Dashboard (existant) + Diff Engine (Phase 14) + Risk Score (Phase 15). Ne construire un vrai module Incident/Investigation séparé que si un besoin concret apparaît. »

Cette implémentation couvre **exactement** cette vue — deux widgets sur le Dashboard existant. Elle ne couvre **pas** un module Incident/Investigation (ticketing, assignation, workflow d'enquête) : ce sous-gate reste non levé par l'override reçu, qui portait sur le prérequis d'usage général de la piste, pas sur ce module explicitement mis à part par le texte lui-même. Aucune nouvelle table, aucun nouveau modèle.

## Constat de l'inspection read-only préalable

Contrairement à ce que le texte de la roadmap laissait supposer, le Dashboard existant (`frontend/app/pages/index.vue`) n'affichait **aucune** donnée de findings ni de changements — uniquement statut système, jobs actifs, scans récents et statistiques d'outils. La couverture réelle des données ("Findings actifs" et "changements récents") existait bien, mais **ailleurs et de façon incomplète** :

- `GET /api/findings` (Phase 16) était déjà une liste **cross-project** filtrable par statut — mais sans raccourci "actif" (il fallait connaître et répéter les 4 statuts non résolus).
- Aucune route ne listait les `AssetChangeEvent` (Phase 14) au-delà d'un seul asset (`GET /api/assets/{id}/changes`). La seule requête cross-asset existante était du code privé, non réutilisable, à l'intérieur de `POST /api/ai/chat`.

Le delta réel à combler était donc précis et petit : un paramètre additif + une route manquante + deux widgets d'affichage.

## Changements

### Backend

- **`GET /api/findings`** (`app/api/routes/findings.py`) : nouveau paramètre `active_only: bool = False`, additif et rétrocompatible. Raccourci pour `status IN (NEW, CONFIRMED, IN_REVIEW, REOPENED)` (la définition exacte de "actif" du state machine Phase 16 — exclut `ACCEPTED_RISK`/`FALSE_POSITIVE`/`REMEDIATED`, des issues résolues, pas du silence). Ignoré si `status` est fourni explicitement — un filtre explicite gagne toujours.
- **`GET /api/asset-changes`** (nouveau, `app/api/routes/schedules.py`) : équivalent cross-project de `GET /api/assets/{id}/changes`, même filtres (`change_type`, `severity`, `limit`, `before`) plus un `project_id` optionnel. Généralise le pattern de jointure déjà utilisé en privé dans `POST /api/ai/chat` (`Asset.project_id`). Un `project_id` qui ne correspond à rien retourne une liste vide, jamais une 404 — même convention que `GET /api/findings?project_id=`.

### Frontend

- **`ActiveFindingsWidget.vue`** / **`RecentChangesWidget.vue`** (nouveaux, `frontend/app/components/`) : deux widgets autonomes (propre fetch/chargement/erreur, même patron que `AssetChangeTimeline.vue`), montés sur `pages/index.vue`. `RecentChangesWidget.vue` duplique volontairement la petite logique de résumé/icône déjà présente dans `AssetChangeTimeline.vue` plutôt que de la partager — même précédent que d'autres petits helpers dupliqués ailleurs dans ce code base.
- **`types/asset-change-event.ts`** (nouveau) : type précédemment déclaré uniquement en inline dans `AssetChangeTimeline.vue`, factorisé pour être partagé sans dupliquer la forme complète.

## Ce qui n'est délibérément pas fait

- **Aucun module Incident/Investigation.** Reste gated par le texte de la roadmap lui-même, non additionnellement levé.
- **Aucune nouvelle table/modèle.** Uniquement des vues sur des données déjà réelles (Finding, AssetChangeEvent).
- **Aucun compteur agrégé nouveau** (ex: "12 findings actifs") sur le Dashboard : les widgets n'affichent que les 8 éléments les plus récents/prioritaires récupérés — annoncer un total à partir d'une liste tronquée aurait été trompeur.

## Vérification en conditions réelles

`curl` authentifié contre la base de dev réelle : `active_only=true` retourne des findings réels non résolus (`whatweb`/DVWA) ; `GET /api/asset-changes` retourne des événements de changement réels (`TECHNOLOGY_REMOVED` sur DVWA), triés du plus récent au plus ancien. UI vérifiée visuellement : les deux nouveaux widgets apparaissent au bon endroit sur le Dashboard, avec le bon en-tête et le bon état de chargement — le round-trip complet jusqu'au rendu des données n'a pas pu être bouclé dans le navigateur de test pour la même raison déjà documentée en Phase 24 (`NUXT_PUBLIC_API_BASE` pointe vers l'IP LAN réelle, injoignable depuis ce bac à sable — confirmé en observant que les tuiles de statut système, elles aussi préexistantes et non modifiées, restent bloquées sur "checking" pour la même raison).

## Tests

- Backend : `tests/findings/test_findings_api.py` (+4 : active_only inclut/exclut les bons statuts, `status` explicite l'emporte, comportement par défaut inchangé), `tests/scheduling/test_asset_changes_global_api.py` (nouveau, 9 tests : multi-projets, filtre `project_id` — y compris un id inconnu qui ne 404 jamais — sévérité, type, tri, pagination `limit`/`before`).
- Frontend : `ActiveFindingsWidget.test.ts` (5), `RecentChangesWidget.test.ts` (4) : requête correcte au montage, état vide, état d'erreur, rendu du contenu réel.

## Migration

Aucune. `Finding.status` et `AssetChangeEvent` existaient déjà tels quels (Phases 14/16).
