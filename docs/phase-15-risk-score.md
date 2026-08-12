# Phase 15 — Risk Intelligence & Risk Score

## Objectif

Répondre à : *« Parmi tous les Findings actuels, lesquels dois-je traiter en priorité ? »* avec un score **explicable, déterministe, local-first** — jamais une boîte noire IA, jamais `severity = HIGH → score = 90`.

## Audit initial — écart entre la roadmap et le code réel

Avant implémentation, vérification de l'état réel (pas supposé) :

- **Aucun champ CVE/CVSS n'existait nulle part** dans `Finding` ni dans les parsers. `app/tools/parsers/nuclei.py` ne capturait que `template_id`/`name`/`severity`/`matched_at`/`description` — le bloc `info.classification` de nuclei (qui porte `cve-id`/`cvss-score`/`cvss-metrics`) n'était pas parsé du tout.
- **Vérifié en conditions réelles, pas supposé** : un template nuclei de contrôle a été exécuté via le vrai binaire `nuclei` (v3.11.0) dans `cyberlab-kali` pendant l'audit, confirmant le schéma JSON exact : `info.classification.cve-id` est un **tableau de chaînes en minuscules** (`["cve-2021-44228"]`), `cvss-metrics` porte le vecteur complet avec préfixe de version (`CVSS:3.1/...`), `cvss-score` un flottant.
- `Finding.confidence` existe et est utilisé tel quel — actuellement tous les extracteurs le laissent à la valeur par défaut du modèle (`MEDIUM`), aucun ne le différencie encore. C'est une donnée réelle (pas inventée), juste non différenciée aujourd'hui — documenté honnêtement plutôt que masqué.
- Les 3 sources externes (FIRST.org EPSS, CISA KEV, NVD CVE API 2.0) ont été **appelées réellement** pendant l'audit pour confirmer leurs schémas JSON exacts avant d'écrire le moindre code de parsing — voir ci-dessous.

## Vulnerability Intelligence — stratégie d'ingestion

Trois tables locales (`backend/app/models/vulnerability_intel.py`), scope volontairement limité :

| Table | Contenu | Stratégie |
|---|---|---|
| `vulnerability_intel` | CVSS + EPSS, **un CVE à la fois** | Uniquement les CVE **effectivement rencontrés** dans un Finding (`known_cve_ids()` scanne `Finding.cve_ids`) — jamais un dump NVD/EPSS complet. |
| `cisa_kev_entries` | Catalogue CISA KEV complet | **Téléchargement complet justifié** : contrairement à EPSS, CISA ne publie aucune API de requête par CVE — un seul fichier JSON officiel, ~1 665 entrées, ~1,5 Mo (vérifié en conditions réelles) — borné et raisonnable pour un outil local. |
| `intel_sync_state` | Une ligne par source (`epss`/`cisa_kev`/`nvd`) | `last_attempt_at`/`last_success_at`/`last_error` — distingue *« jamais synchronisé »* de *« synchronisé, résultat négatif »* (voir KEV ci-dessous). |

### EPSS

`app/intel/epss.py` — `GET https://api.first.org/data/v1/epss?cve=A,B,C` (lot de 100 CVE max par requête, pas de clé API). Conserve `epss_score`, `epss_percentile`, `epss_fetched_at`. Un CVE absent de la réponse n'est pas une erreur — `epss_score` reste `NULL`, affiché **`EPSS: N/A`**, jamais une valeur inventée.

### CISA KEV

`app/intel/cisa_kev.py` — catalogue complet remplacé à chaque sync (upsert + suppression des entrées disparues). `knownRansomwareCampaignUse` (`"Known"`/`"Unknown"`) converti en booléen strict (`== "Known"`).

**Distinction YES / NO / UNKNOWN** (exigée par la spec) :
- `IntelSyncState("cisa_kev").last_success_at` jamais renseigné → **UNKNOWN** pour *tout* CVE (personne n'a encore vérifié).
- Une fois synchronisé au moins une fois → chaque CVE est **YES** (présent dans `cisa_kev_entries`) ou **NO** (absent) — jamais un troisième état par CVE, puisque le catalogue entier est local.

### NVD / CVSS

`app/intel/nvd.py` — `GET https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=...`, appelé **uniquement pour les CVE sans CVSS connu** (`vulnerability_intel.cvss_score IS NULL`). Priorité de version vérifiée en conditions réelles : `cvssMetricV40 > V31 > V30 > V2`, la version effectivement utilisée est toujours conservée (`cvss_version`) — **jamais deux versions mélangées comme si elles étaient comparables**. Limité à `NVD_MAX_CVES_PER_RUN = 20` par cycle, `NVD_MIN_INTERVAL_SECONDS = 6.5` entre appels (limite non-authentifiée NVD : ~5 req/30s).

**Le CVSS déjà fourni par un outil est prioritaire et n'est jamais écrasé** : `app/risk/service.py::seed_cvss_from_tool()` alimente `vulnerability_intel` immédiatement à l'extraction (nuclei fournit son propre `cvss-score` dans la majorité des templates CVE) — `sync_nvd_cvss()` ne requête donc NVD que pour les CVE qu'aucun outil n'a renseignés.

### Background sync — pas un nouveau service

`app/intel/sync.py::start_intel_sync_thread()` — thread démon dans le process `cyberlab-worker` existant, **distinct du ticker Continuous Recon (Phase 14)** : `ScheduledJob`/le ticker sont spécifiquement « exécuter un outil Kali sur un Asset via le Policy Engine » — l'ingestion d'intelligence n'est pas un scan, la forcer dans ce modèle aurait exigé un faux `asset_id` et une revérification d'autorisation qui n'a pas de sens ici. Le *pattern* (thread de fond dans le worker existant, état suivi en Postgres) est réutilisé ; le *modèle* ScheduledJob ne l'est pas.

Intervalle par défaut 24h (`intel_sync_interval_seconds`). `POST /api/intelligence/sync` déclenche un cycle immédiat via la queue RQ existante (`queue.enqueue(run_full_sync)`) — même substrat d'exécution que les Jobs, pas un nouveau mécanisme, retourne `202` sans jamais bloquer sur un appel réseau.

**Panne d'une source = pas de casse globale** : les trois sync (`sync_cisa_kev`, `sync_epss`, `sync_nvd_cvss`) sont chacune encapsulées individuellement dans `run_full_sync()` — testé (`test_run_full_sync_one_source_crashing_does_not_prevent_others`).

## Risk Calculator — formule exacte

`app/risk/calculator.py`, pure, déterministe, sans I/O, sans LLM.

### Normalisation (pas d'addition brute d'échelles incomparables)

Trois signaux, chacun ramené sur **[0, 1]** :

```
technical_severity  = cvss_score / 10.0                         si CVSS connu
                     = fallback_sévérité(severity)               sinon (toujours disponible)
                       fallback: INFO=0.00 LOW=0.25 MEDIUM=0.55 HIGH=0.80 CRITICAL=0.95
                       (points médians des bandes qualitatives CVSS officielles)

exploitation_prob    = epss_score                                si EPSS connu (déjà 0-1)
                       sinon EXCLU du calcul (jamais remplacé par 0 ou 0.5)

known_exploited      = 1.0 si KEV=true, 0.0 si KEV=false (confirmé)
                       sinon EXCLU du calcul (KEV jamais deviné)
```

### Agrégation — moyenne pondérée des signaux *disponibles uniquement*

```
poids nominaux : technical_severity=0.40  exploitation_prob=0.35  known_exploited=0.25

raw_score = Σ(valeur_i × poids_i, pour i disponible) / Σ(poids_i, pour i disponible)
```

`technical_severity` est toujours disponible (fallback sur `severity`, jamais absent). Si EPSS et/ou KEV manquent, leur poids est simplement retiré du dénominateur — **jamais une valeur inventée n'entre dans la moyenne**.

### Modificateurs contextuels — multiplicatifs, pas dans la moyenne

Criticité d'Asset et Confidence du Finding sont **toujours** disponibles (jamais de valeur manquante) — elles décrivent *combien cette vulnérabilité compte ici*, pas *à quel point elle est grave dans l'absolu* : traitées comme des multiplicateurs plutôt que comme un terme additionnel de plus dans la moyenne pondérée (qui les aurait fait entrer en compétition avec CVSS/EPSS/KEV pour une part fixe du score).

```
criticality_multiplier = LOW:0.85  MEDIUM:1.00  HIGH:1.15  CRITICAL:1.30
                          (pas d'Asset lié → 1.00, neutre)
confidence_multiplier  = LOW:0.60  MEDIUM:0.85  HIGH:1.00

final    = clamp(raw_score × criticality_multiplier × confidence_multiplier, 0, 1)
score    = round(final × 100), borné [0, 100]
```

### Bandes de priorité (conservées telles que spécifiées)

```
0–19   INFORMATIONAL
20–39  LOW
40–59  MEDIUM
60–79  HIGH
80–100 CRITICAL
```

### Justification mathématique

- **Pas d'addition brute** : CVSS (0–10), EPSS (0–1 probabilité), KEV (booléen) et criticité (catégorielle) n'ont ni la même échelle ni la même sémantique — les additionner directement (`CVSS + EPSS×100 + KEV×20 + ...`) produirait un nombre sans signification calculable. Chaque signal est ramené sur [0,1] avant toute combinaison.
- **Moyenne pondérée plutôt que somme** pour les 3 signaux de vulnérabilité : une somme pondérée simple (`Σ valeur×poids` sans diviser par `Σ poids`) pénaliserait injustement un Finding pour qui EPSS/KEV manquent (leur absence ferait mécaniquement chuter le score au lieu de le laisser refléter honnêtement les signaux réellement disponibles) — la division par le poids total disponible corrige ce biais.
- **Multiplicateurs plutôt qu'un 4ᵉ terme pondéré pour criticité/confidence** : un exemple concret a été vérifié pendant le développement — `Asset LOW + CVSS 6.0 (sans EPSS/KEV)` doit rester nettement inférieur à `Asset CRITICAL + même CVE`, mais un Finding déjà très sévère (CVSS 10 + EPSS élevé + KEV) sur un Asset `LOW` ne doit **pas** être noyé/écrasé par un poids fixe de criticité — le multiplicateur (0.85× à 1.30×) préserve l'ordre de grandeur du signal technique tout en l'ajustant, plutôt que de le diluer dans une moyenne à 5 termes.
- **KEV pèse fort sans jamais forcer 100 à lui seul** : testé explicitement (`test_kev_true_alone_does_not_force_maximum_score`) — `KEV=true` seul (sans CVSS/EPSS élevés) plafonne autour de 70–75, jamais 100 ; il faut la combinaison CVSS élevé + EPSS élevé + KEV + Asset CRITICAL + Confidence HIGH pour atteindre 100.
- **Confidence LOW plafonne le score** : testé (`test_low_confidence_finding_never_reaches_maximum_even_with_extreme_signals`) — même avec CVSS 10 + EPSS 1.0 + KEV + Asset CRITICAL, `Confidence: LOW` (×0.60) empêche structurellement d'atteindre 100.
- **Borne 0–100 garantie mathématiquement**, pas seulement testée : `raw_score ≤ 1.0` (moyenne pondérée de valeurs ≤1) × `criticality_multiplier ≤ 1.30` × `confidence_multiplier ≤ 1.00` = `≤ 1.30`, explicitement clampé à `1.0` avant conversion en score — testé sur le cas extrême (`CVSS 10 + EPSS 1.0 + KEV + CRITICAL + HIGH ≤ 100`).

### Exemple réel vérifié (Phase 15 E2E, CVE-2021-44228 / Log4Shell)

```
CVSS 10.0 (3.1), EPSS 99.999%, KEV=true, Asset LOW, Confidence MEDIUM
→ raw_score = (1.0×0.40 + 0.99999×0.35 + 1.0×0.25) / 1.0 = 0.9999965
→ final = 0.9999965 × 0.85 × 0.85 = 0.7225
→ score = 72, priority = HIGH

Même Finding après passage de l'Asset à CRITICAL :
→ final = 0.9999965 × 1.30 × 0.85 = 1.1049 → clamp 1.0
→ score = 100, priority = CRITICAL
```

Valeurs réelles observées via `GET /api/findings/{id}/risk` contre le stack Docker, pas une simulation.

## Stockage — score matérialisé, recalcul déclenché

`Finding` gagne 6 colonnes nullables : `cve_ids`, `cvss_score`, `epss_score`, `kev`, `risk_score`, `risk_priority`, `risk_calculated_at` — cache du dernier calcul, jamais la source de vérité (qui reste `vulnerability_intel`/`cisa_kev_entries`/l'Asset lié).

**Recalcul déclenché** (`app/risk/service.py`), jamais à chaque lecture :
1. À l'extraction du Finding (`app/jobs/tasks.py::execute_job`) — calcul immédiat avec l'intelligence disponible à cet instant.
2. Après une sync EPSS/KEV/NVD réussie — `recalculate_findings_for_cve()` / `recalculate_all_findings_with_cve()` (uniquement les Findings concernés).
3. Après changement de `Asset.criticality` (`PATCH /api/assets/{id}`) — `recalculate_findings_for_asset_sync()`, dispatché via `asyncio.to_thread` pour ne jamais bloquer la boucle d'événements asynchrone.

`GET /api/findings/{id}/risk` **recalcule en direct** (pur CPU, aucun appel réseau) plutôt que de faire confiance aveuglément au cache — garantit une reproductibilité totale même si un déclencheur de recalcul avait été manqué. `GET /api/findings` (liste/tri/filtres) utilise le cache matérialisé pour rester rapide même avec plusieurs centaines de Findings.

## API

```
GET  /api/findings?priority=&kev=&min_risk_score=&sort=risk_score_desc|risk_score_asc|created_at_desc
GET  /api/findings/{id}/risk
GET  /api/assets/{id}/risk-summary
POST /api/intelligence/sync      (202, enqueue RQ)
GET  /api/intelligence/status
```

Toutes authentifiées (vérifié explicitement dans `test_every_api_route_is_guarded_when_auth_enabled`), aucune n'effectue d'appel réseau externe synchrone.

## Vérification end-to-end réelle

1. **Écart de comportement découvert et documenté** : le premier essai d'un scan nuclei réel a échoué (`no templates provided for scan`) — cause réelle trouvée : le filtre de sévérité par défaut du profil nuclei (`info,low,medium`) exclut un template `critical` si aucune sévérité n'est explicitement demandée. Corrigé en passant `severity: critical` dans les options du job — comportement du Tool Registry (Phase 3), pas un bug de cette phase, mais un piège réel rencontré et documenté plutôt que contourné en silence.
2. **CVE réel bout en bout** : job `nuclei` réel contre le lab DVWA (via un template nuclei réel référençant CVE-2021-44228/Log4Shell, choisi pour avoir des données EPSS/KEV publiques authentiques) → Finding créé avec `cve_ids`, `cvss_score=10.0`/`cvss_version=3.1` immédiatement seedés depuis le template.
3. **Sync réelle déclenchée** via `POST /api/intelligence/sync` (exécutée par le vrai worker RQ) → appels HTTP réels observés dans les logs vers `cisa.gov` et `api.first.org` → `epss_score=0.99999`, `kev=true` réellement peuplés.
4. **Score et explication vérifiés** via `GET /api/findings/{id}/risk` : `72/HIGH` avec Asset `LOW`, décomposition complète (CVSS/EPSS/KEV/criticité/confidence) et 5 lignes d'explication humaine.
5. **Changement de criticité réel** : `PATCH /api/assets/{id}` LOW→CRITICAL → score recalculé automatiquement à `100/CRITICAL`, vérifié à nouveau via l'API.
6. **UI réelle** (navigateur) : page Findings (Top Risks au format demandé, filtres KEV/priority/min-score, tri par Risk Score), page de détail Finding (Risk Analysis + Why this score?), Risk Overview sur la page Asset (Critical/High/KEV findings, highest risk score) — tous vérifiés avec les données réelles ci-dessus.
7. Nettoyage complet (template de test retiré du conteneur Kali, projet/asset/lab de test supprimés), logs `cyberlab-api`/`cyberlab-worker` vérifiés sans erreur.
8. Suite de tests complète (292 tests, dont 81 nouveaux) rejouée contre une base `_test` fraîchement recréée : verte.

## Performance

- Aucun appel réseau externe par Finding ni par requête de lecture — uniquement en tâche de fond.
- EPSS/NVD limités aux CVE réellement rencontrés (jamais un dump complet).
- `GET /api/findings` trie/filtre sur les colonnes matérialisées (`risk_score`, `kev`, `risk_priority`) — pas de recalcul à la volée sur une liste.
- `find_previous_comparable_job`-style : les recalculs après sync ne scannent que les Findings concernés (par CVE) ou l'ensemble borné des Findings liés à un Asset — jamais l'historique complet du système.

## Audit sécurité

Voir la section dédiée dans [security.md](security.md#phase-15--risk-intelligence--risk-score--audit-de-sécurité).

## Limites connues / hors scope

- `Finding.confidence` reste uniformément `MEDIUM` (aucun extracteur ne le différencie encore) — donnée réelle utilisée telle quelle, pas une limite du Risk Score lui-même mais un signal encore peu informatif en amont.
- Seul nuclei alimente `cve_ids`/CVSS automatiquement ; searchsploit ne fournit pas de CVE fiable dans les données actuellement capturées (pas d'extraction inventée).
- Pas de rétro-calcul des scores pour les Findings créés avant la Phase 15 (visibles comme `UNSCORED` dans l'UI) — honnête plutôt que simulé.
- Pas de corrélation entre Findings de plusieurs outils sur un même CVE/service (Phase 16).
