# CyberLab — Roadmap révisée (Phases 13+)

> Ce document remplace et critique `CyberLab_Roadmap_V2_V3.md` (le brouillon initial fourni). Il part du même horizon (faire évoluer CyberLab au-delà d'un simple frontend pour Kali) mais le confronte à ce que CyberLab **est réellement aujourd'hui** — un outil local, mono-utilisateur, Docker Compose, sans comptes ni multi-tenance — plutôt que de lister des fonctionnalités de plateforme SaaS d'entreprise sans lien avec cette réalité.

---

## 0. Résumé exécutif

Le brouillon V2/V3 original contient de bonnes idées (Asset Model, Security Graph, Continuous Recon, Correlation Engine, Risk Scoring, AI Copilot, Evidence Management) noyées dans **53 sections** dont une bonne partie (Multi-Tenant, SSO, Billing, Event Bus, Multi-Kali distribué, Plugin marketplace, RBAC/ABAC entreprise, CLI+SDK comme produit public) décrit essentiellement *"comment transformer CyberLab en Splunk/Rapid7"* — une v0 → v100 sans étapes intermédiaires réalistes, sans lien avec l'architecture réelle du projet (un seul conteneur Kali, un seul worker RQ, aucune notion de compte utilisateur — [security.md](security.md) documente d'ailleurs explicitement pourquoi le RBAC a été volontairement différé en Phase 11 faute d'identité utilisateur).

Cette révision :

1. **Garde** les idées à forte valeur qui prolongent naturellement le travail déjà fait (Phases 1–12) : modèle Asset, graphe de sécurité léger, reconnaissance continue, corrélation, scoring de risque, copilote IA multi-agents *contraint par le Policy Engine existant*, gestion des preuves, Tool Orchestrator.
2. **Ancre** ces idées dans des pratiques réelles trouvées par recherche (EPSS+CVSS+CISA KEV pour le scoring de risque, architectures ASM open-source, patterns multi-agents SOC 2026, graphes de connaissance type BRON reliant CVE/CWE/CAPEC/ATT&CK) — voir [Sources](#sources).
3. **Coupe ou reporte explicitement** ce qui ne correspond pas à un outil local mono-utilisateur, avec la raison à chaque fois (section [7](#7-explicitement-hors-scope-et-pourquoi)) — dans le même esprit que l'exclusion documentée de hydra/john/hashcat en Phase 12 (`docs/tools.md`) : un choix assumé, pas un oubli.
4. **Numérote la suite à partir de la Phase 13**, dans le style déjà établi par le projet (un phase = un livrable testé et vérifié en conditions réelles, pas une liste de vœux).

---

## 1. Où en est réellement CyberLab (Phases 1–12)

Avant de planifier la suite, un état des lieux honnête — c'est le principal angle mort du document original, qui ne référence jamais l'implémentation existante :

| Domaine | État réel |
|---|---|
| Infra | Docker Compose local : `cyberlab-api` (FastAPI), `cyberlab-worker` (1 worker RQ), `cyberlab-postgres`, `cyberlab-redis`, `cyberlab-kali` (isolé, `cap_add: [NET_RAW]` narrow), `cyberlab-labmanager` (non-root, via `cyberlab-docker-proxy`), `cyberlab-frontend` (Nuxt 4). Ollama tourne sur l'hôte, non conteneurisé. |
| Modèle de données | `Project` → `Target` (`authorization_status`: `UNKNOWN`/`LAB`/`AUTHORIZED`/`LOCAL`) → `Job` (`tool`+`profile`+`params`+`status`+`result`) → `Finding` (sévérité/confiance/evidence) → `Report` (HTML/MD/JSON/PDF). |
| Tool Registry | 31 outils curés (pas un dump Kali), profils nommés, `risk_level` (`SAFE`/`CAUTION`/`RESTRICTED`/`MANUAL_ONLY`), `ai_allowed` réellement appliqué à deux niveaux (prompt + revalidation), Tool Health non destructif. Voir `docs/tools.md`. |
| IA | Provider Ollama abstrait, Analyst (analyse post-hoc), Mission Planner (propose tool+profile, jamais n'exécute), Assistant chat conscient du contexte réel (target actif, catalogue d'outils). L'IA n'a **aucun** accès direct à `subprocess`/`docker.sock`/écriture sur `Target` — vérifié par tests statiques. |
| Sécurité | Policy Engine = un seul point d'application (`POST /api/jobs`, vérifie `is_executable(target)`). `AUTH_ENABLED` optionnel (bearer token unique, pas de comptes). Docker Socket Proxy. Terminal PTY confiné mais volontairement sans allowlist. 152 tests, audit structuré par phase (`docs/security.md`), plusieurs vraies vulnérabilités trouvées et corrigées (XSS rapports, injection PDF, crash agent sur timeout, etc.). |
| Multi-utilisateur | **Inexistant.** Un seul secret partagé, pas de table `users`, pas de RBAC — décision explicitement documentée (`docs/security.md#rbac`). |
| Échelle | Un seul conteneur Kali, une seule queue RQ séquentielle. Pas de workers distribués, pas de scheduler multi-nœud. |
| Connu et assumé comme limite | Le chemin `target` texte libre (`POST /api/jobs` sans `target_id`) contourne l'autorisation — hérité des Phases 3–9, documenté, pas corrigé pour ne pas casser la compatibilité. |

**Conséquence directe pour la suite** : toute proposition qui suppose des comptes utilisateurs, une flotte de workers, ou une architecture microservices doit soit (a) construire d'abord les fondations manquantes explicitement, soit (b) être reportée. Le document original saute directement à "Multi-Tenant Architecture" (section 45) sans jamais mentionner qu'il n'existe même pas un deuxième utilisateur.

---

## 2. Critique ciblée du document original

Pour être constructif plutôt que juste négatif, voici précisément ce qui pose problème et pourquoi :

- **Aucune priorisation ancrée dans le coût réel.** Les 53 sections sont présentées à plat, puis "priorisées" en listant... les mêmes 53 sections dans un ordre différent (section "Priorités recommandées"), sans jamais dire *pourquoi* ni *combien ça coûte*. Une vraie roadmap doit distinguer un weekend de travail (ex: ajouter `EPSS` à l'affichage d'un finding) d'un trimestre (ex: "Multi-Agent Security System").
- **Confusion entre "outil de recherche/lab personnel" et "plateforme SOC d'entreprise".** Des sections comme *44. Advanced RBAC/ABAC*, *45. Enterprise/Multi-Tenant*, *48. Event Bus*, *22/23. Distributed Execution / Multi-Kali* sont copiées du vocabulaire des plateformes commerciales (Rapid7, Tenable, Splunk) sans jamais se demander si CyberLab, dans son usage réel (un chercheur, un CTF, un audit autorisé), en a besoin. Répondre "peut-être un jour" à tout finit par diluer ce qui compte vraiment.
- **Duplication et incohérence interne.** *3. Security Graph* (V2) et *37. Security Knowledge Graph 3.0* (V3) décrivent presque la même chose deux fois avec des mots différents. *20. Threat Intelligence* et *21. Vulnerability Intelligence* se recoupent largement. *16. Lab Factory* et *40. Cyber Range Platform* aussi. Une roadmap doit consolider, pas empiler.
- **"AI Autonomy Levels" définis mais jamais reliés à ce qui existe.** La section 10 invente des niveaux 0–4 sans mentionner que CyberLab a *déjà* un mécanisme équivalent et fonctionnel : le Policy Engine + `ai_allowed` + l'authorization Target (Phases 11–12). La bonne approche est d'étendre ce qui marche, pas de le réinventer sous un autre nom.
- **Pas de section "ce qu'on ne fait pas".** Une roadmap sérieuse dit explicitement quoi refuser. Celle-ci ne refuse jamais rien — chaque idée reste "à faire un jour", ce qui n'aide pas à décider quoi faire *ensuite*.
- **Recherche absente.** Aucune référence à comment les vrais outils (ASM open-source, scoring EPSS, graphes ATT&CK) font ça concrètement — d'où des propositions vagues ("Threat Intelligence: Enrichment, Correlation, Reputation...") qu'on ne sait pas implémenter. Cette révision comble ce point (voir [Sources](#sources)).

---

## 3. Principes directeurs (révisés)

En complément du principe original ("CyberLab ne doit pas devenir *Kali avec une jolie interface*", qui reste juste) :

1. **Chaque phase reste un livrable vérifié en conditions réelles**, pas une liste de fonctionnalités. C'est ce qui a permis de trouver et corriger de vraies régressions à chaque phase (`CHANGELOG.md`) — ne pas l'abandonner en accélérant le rythme.
2. **N'ajouter une couche d'infrastructure que quand la précédente est saturée**, pas par anticipation. Un seul worker RQ suffit tant qu'aucune mission ne dépasse quelques minutes ; ne construire "Distributed Execution" que le jour où c'est mesurablement un goulot d'étranglement.
3. **L'IA gagne en autonomie *au sein* du Policy Engine existant, jamais à côté.** Un "Multi-Agent System" n'est acceptable que si chaque agent passe par le même point d'application unique que `POST /api/jobs` aujourd'hui — jamais un nouveau chemin d'exécution parallèle.
4. **Préférer les sources de données gratuites et locales** (NVD API, EPSS de FIRST.org, flux JSON CISA KEV — tous sans clé API) à des intégrations commerciales, cohérent avec la philosophie "outil local" de CyberLab.
5. **Documenter ce qu'on refuse de construire, pas seulement ce qu'on construit** — voir section 7.

---

## 4. Vue d'ensemble des pistes retenues

```text
                        CyberLab (Phases 1-12, existant)
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
   TRACK A                     TRACK B                     TRACK C
Asset & Risk               AI Copilot                  Workflow &
Intelligence                Evolution                   Reporting
        │                           │                           │
 Asset Model              Multi-Agent (contraint         Evidence & Chain
 Security Graph            par le Policy Engine)          of Custody
 Continuous Recon          AI Memory                     Reports 2.0
 Correlation Engine        Mission Refinements           Tool Orchestrator
 Risk Score                                              Lab Factory 2.0
 (EPSS+CVSS+KEV)                                          Pentest Workspace
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                    Plus tard, si le besoin est prouvé :
              Attack Path (léger, local) · SOC-lite · Multi-Kali (opt-in)
```

---

## 5. Track A — Asset & Risk Intelligence

### Phase 13 — Asset Model (évolution de Target)

**Objectif** : faire évoluer `Target` vers un vrai modèle `Asset`, sans casser l'existant (migration additive, comme toujours).

- `Asset` généralise `Target` : `type` élargi (`IP`/`HOST`/`DOMAIN`/`SUBDOMAIN`/`URL`/`SERVICE`/`CONTAINER`/`LAB_RESOURCE` — pas la liste complète du brouillon original qui inclut `Cloud resource`/`Database`/`API` sans que CyberLab ait de connecteur pour les découvrir ; ajouter ces types seulement quand un mécanisme de découverte existe réellement pour eux).
- Champs réalistes : `criticality` (LOW/MEDIUM/HIGH/CRITICAL, saisi manuellement — pas de calcul automatique tant que le Risk Score de la Phase 15 n'existe pas), `tags`, `first_seen`/`last_seen` (calculés à partir des jobs liés, pas un champ éditable), `technologies` (alimenté par les résultats whatweb/nuclei déjà collectés).
- `Target` devient un cas particulier d'`Asset` (renommage progressif en base, vue de compatibilité pour ne rien casser côté API existante) plutôt qu'une table séparée en doublon.
- **Ne pas faire** : la liste du brouillon original propose aussi `Cloud resource`, `Workstation`, `Database` comme types d'Asset — les garder dans le schéma comme valeurs `OTHER` typées jusqu'à ce qu'un vrai mécanisme de découverte cloud/DB existe ; un type sans découverte associée n'est qu'un menu déroulant vide.

**Complexité** : M (moyenne) — migration de données existantes, pas seulement additive cette fois (renommage conceptuel).

### Phase 14 — Reconnaissance continue & détection de changement

**Objectif** : transformer un scan ponctuel en surveillance périodique, en réutilisant le Job Engine existant plutôt qu'un nouveau moteur.

- Scan planifié : un `ScheduledJob` (cron simple, RQ Scheduler ou APScheduler côté worker — pas besoin d'un nouveau service) qui recrée périodiquement un job existant avec les mêmes tool/profile/target.
- Diff Engine : comparer `Job.result` (déjà normalisé par les parsers) entre deux exécutions consécutives sur le même Asset → générer un `AssetChangeEvent` (nouveau port, port fermé, nouvelle techno, certificat modifié). Réutilise directement les `NormalizedResult` de la Phase 12 (`{"hosts": [...]}`, `{"results": [...]}`, etc.) — pas de nouveau format à inventer.
- UI : timeline de changements sur la page Asset, pas un nouveau module séparé.
- **Portée volontairement réduite vs le brouillon** : pas de "surveillance des DNS/certificats/endpoints" comme processus indépendants — tout passe par le Job Engine existant avec une planification, en réutilisant les outils déjà enregistrés (dig, sslscan, testssl, subfinder…).

**Complexité** : M.

### Phase 15 — Risk Score (ancré sur des données réelles, gratuites)

**Objectif** : remplacer une "Threat Intelligence" vague par un score de risque composite construit sur des sources publiques et sans clé API, conformément aux pratiques actuelles ([Picus](https://www.picussecurity.com/resource/blog/vulnerability-prioritization-why-cvss-isnt-enough), [Intruder](https://www.intruder.io/blog/epss-vs-cvss)) :

```text
Finding (CVE identifié, ex. via nuclei/searchsploit)
   ↓
CVSS  (sévérité technique — déjà présent si le finding cite un CVE)
   ↓
EPSS  (probabilité réelle d'exploitation — api.first.org/data/v1/epss, gratuit, sans clé)
   ↓
CISA KEV (déjà activement exploité en conditions réelles — flux JSON public, gratuit)
   ↓
Criticité de l'Asset (Phase 13, saisie manuelle)
   ↓
CyberLab Risk Score = f(CVSS, EPSS, KEV, criticité asset, confiance du finding)
```

- Combiner CVSS+EPSS+KEV réduit la charge de priorisation "urgente" jusqu'à 95 % dans la pratique observée ([Cymulate](https://cymulate.com/blog/how-to-prioritize-vulnerabilities/)) — un signal bien plus actionnable qu'un score interne inventé sans base publique.
- Import : job planifié (Phase 14) qui télécharge le flux EPSS quotidien (CSV/JSON, ~mise à jour journalière) et le flux CISA KEV (JSON), les stocke localement (une table `vulnerability_intel` mise à jour en tâche de fond) — aucun appel réseau synchrone dans le chemin critique de scoring.
- Le score reste **affiché avec sa décomposition** (CVSS = X, EPSS = Y%, KEV = oui/non) plutôt qu'un simple nombre opaque — cohérent avec la sévérité toujours conservatrice déjà pratiquée dans `app/findings/extractor.py`.
- **Ne pas faire** : le brouillon original propose un "CyberLab Risk Score" qui mélange CVSS/exposition/criticité/exploitabilité/confiance/impact/contexte projet en une seule formule opaque sans préciser comment. Rester sur la formule CVSS+EPSS+KEV éprouvée plutôt que d'inventer une pondération arbitraire de 7 facteurs.

**Complexité** : S/M — les APIs sont gratuites et documentées, le travail est surtout dans l'ingestion planifiée et l'affichage.

### Phase 16 — Corrélation & déduplication

**Objectif** : réutiliser les `Finding` déjà extraits automatiquement (Phase 9) plutôt que refaire un moteur de normalisation — le brouillon original (section 5 "Unified Findings Engine") demande de renormaliser des outils déjà normalisés depuis la Phase 3.

- Déduplication : deux findings du même `source_tool` sur le même `Asset`/port avec la même signature (`title` normalisé) → fusion, en gardant `first_seen`/`last_seen` et un compteur d'observations plutôt que des doublons.
- Corrélation cross-outils *simple d'abord* : si nmap détecte un port HTTP ouvert et que whatweb identifie une techno dessus dans la même fenêtre temporelle sur le même Asset, lier les deux `Finding` (`related_finding_ids`) — pas de moteur de règles générique dès le départ, quelques règles concrètes codées en dur (nmap↔whatweb, nmap↔nuclei) suffisent pour prouver la valeur avant de généraliser.
- Cycle de vie du Finding (reprendre du brouillon, c'est une bonne idée sous-exploitée dans CyberLab actuel) : `NEW → CONFIRMED → IN_REVIEW → ACCEPTED_RISK / FALSE_POSITIVE / REMEDIATED → REOPENED`. Simple colonne `status` + historique, pas de workflow engine séparé.

**Complexité** : M.

### Phase 17 — Security Graph (léger, local, pas un nouveau service)

**Objectif** : donner une vue relationnelle Asset↔Finding↔CVE sans introduire une base de données graphe séparée (Neo4j) tant que le volume ne le justifie pas — PostgreSQL suffit largement à l'échelle d'un outil mono-utilisateur.

- Table de relations simple : `graph_edges(from_type, from_id, to_type, to_id, relation)` — couvre `Asset→Service`, `Asset→Finding`, `Finding→CVE`, `Asset→Technology`. Interrogeable en SQL récursif (`WITH RECURSIVE`) pour les besoins réels (2-3 sauts), sans le coût opérationnel d'un second SGBD.
- Inspiration pour la structure des relations : le projet [BRON](https://arxiv.org/pdf/2003.03663) (graphe ouvert reliant ATT&CK/CAPEC/CWE/CVE/D3FEND) — pas besoin de l'importer en entier, mais reprendre son modèle de typage des relations évite de réinventer un schéma ad hoc.
- UI : composant graphe interactif (ex. Cytoscape.js ou Vue Flow, léger, pas de dépendance lourde), zoom/filtre/recherche — repris du brouillon original, c'est une bonne demande, juste pas besoin de Neo4j pour la servir à cette échelle.
- **Ne pas faire tout de suite** : "Attack Path Discovery" automatique (brouillon section 6.3/38) — beaucoup plus dur à bien faire (voir la nuance de BloodHound/[FalconForce](https://falconforce.nl/graphing-mitre-attck-via-bloodhound/) : un chemin d'attaque doit être présenté comme une *hypothèse vérifiable*, pas un fait, sous peine de faux positifs dangereux en contexte pentest). Le graphe de relations de cette phase est le prérequis ; l'analyse de chemins vient après, voir section 6.

**Complexité** : M/L.

---

## 5bis. Chantier transversal — Frontend Architecture & UX (18a–18e)

> **Ceci n'est pas une phase numérotée de la roadmap officielle.** La
> numérotation ci-dessus (13 → 22) reste inchangée ; ce chantier a été
> mené entre la fin de la Phase 17 et le début de la Phase 18 officielle,
> et documenté ici pour que l'historique reste compréhensible sans créer
> de confusion avec la vraie Phase 18 (Agents spécialisés IA, section 6
> ci-dessous — **livrée depuis**, voir
> [phase-18-ai-agents.md](phase-18-ai-agents.md)).

**Objectif** : traiter la dette d'architecture/UX frontend accumulée sur
les Phases 13–17 (color-maps dupliquées, états loading/empty ad hoc,
navigation plate, page Asset de 895 lignes) avant que les Agents IA de la
Phase 18 n'ajoutent encore de la surface au frontend. Aucun changement
backend/API/schéma DB dans ce chantier.

Sous-étapes (référencées telles quelles dans `CHANGELOG.md`, section
*"Cross-cutting — Frontend Architecture & UX (18a–18e)"*) :

- **18a** — types partagés (miroir exact des schémas backend), design
  system centralisé (badges, color-maps par domaine), `LoadingState`/
  `EmptyState`, composables `useAssets()`/`useProjects()`, mise en place
  de Vitest.
- **18b** — navigation hiérarchisée (Attack Surface / Execution & Support),
  renommage `/targets` → `/assets` avec redirections legacy
  `/targets`→`/assets` et `/targets/:id`→`/assets/:id` conservées.
- **18c** — `/graph` (Security Graph global) et `/intelligence` comme
  pages réelles.
- **18d** — découpage de la page Asset (895 → 275 lignes) en composants
  dédiés (`AssetHeader`, `AssetContinuousRecon`, `AssetChangeTimeline`,
  `AssetRiskOverview`, `AssetFindingsList`).
- **18e** — consolidation : audit et correction des duplications
  restantes, accessibilité, vocabulaire Assets/Targets, suppression de
  code mort (`ComingSoon.vue`).

**Résultat vérifié** : 68 tests verts, build et Docker validés,
vérification navigateur réelle (desktop + mobile) sur toutes les routes,
26 erreurs TypeScript préexistantes dans `tools/index.vue` confirmées
comme dette antérieure (non introduites, non masquées). Aucun agent IA
n'a été implémenté à l'occasion de ce chantier.

---

## 6. Track B — Évolution du copilote IA

### Phase 18 — Agents spécialisés (dans le Policy Engine existant)

**Objectif** : reprendre l'idée d'agents spécialisés (Recon/Web/Vulnerability/Report) du brouillon, mais avec la distinction *copilot vs agent* qui structure les architectures SOC 2026 réelles : un copilot répond à une question posée, un agent choisit une hypothèse et va chercher les preuves lui-même ([Security Boulevard, 2026](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/)).

```text
Orchestrateur (nouveau, mais mince)
   │
   ├── Recon Agent     — propose un plan (déjà : Mission Planner)
   ├── Analyst Agent    — analyse un job terminé (déjà : AI Analyst)
   ├── Correlation Agent — lit les Finding + graph_edges, propose des liens (nouveau, LECTURE SEULE)
   └── Report Agent      — assemble un brouillon de rapport à partir des Finding validés (nouveau)
```

- **Contrainte non négociable** : aucun agent n'obtient de nouveau chemin d'exécution. Tous passent par `POST /api/jobs` (Recon Agent) ou ne font que lire (Correlation/Report Agent) — jamais d'écriture directe en base par un agent. C'est l'extension naturelle de ce qui existe déjà (`ai/planner.py` ne fait jamais d'écriture), pas une nouvelle garantie à inventer.
- L'"Orchestrateur" n'est pas un nouveau microservice : une fonction Python qui enchaîne des appels aux providers existants, avec le contexte déjà construit par Target/Project (Phase 11).
- Reprendre les niveaux d'autonomie du brouillon (section 10) mais les relier explicitement à ce qui existe :

  | Niveau | Déjà implémenté ? | Ce que ça veut dire concrètement dans CyberLab |
  |---|---|---|
  | 0 — Advisor | Oui (chat) | L'IA répond, ne propose rien à exécuter. |
  | 1 — Suggest | Oui (Mission Planner) | L'IA propose un plan, l'humain clique "Run" par étape. |
  | 2 — Execute Approved Tasks | Partiel | Un humain valide un plan entier en une fois plutôt qu'étape par étape (à construire). |
  | 3 — Execute Mission Workflow | Non | Une mission avec plusieurs étapes enchaînées automatiquement *si* chaque étape reste `ai_allowed` et que la target reste autorisée — nécessite un mécanisme d'arrêt (kill switch) avant d'exister. |
  | 4 — Autonomous Lab Operations | Non, et à ne construire *que* dans un Lab (jamais AUTHORIZED/LOCAL) | Réservé aux conteneurs de labs jetables (Phase 7) — jamais une cible réelle. |

**Complexité** : M — le plus dur n'est pas le code, c'est de résister à la tentation de donner un chemin d'exécution direct à un agent "pour aller plus vite".

**Résultat réel** : Niveau 2 livré (`Mission`/`MissionStep`/`MissionOrchestrator`) — un plan approuvé une fois s'exécute étape par étape sans reconfirmation humaine, chaque étape revalidée par `is_executable()`/`prepare_job()` avant de partir, jamais un chemin d'exécution parallèle à `POST /api/jobs`. Niveau 3 **non livré comme autonomie complète** (pas d'enchaînement conditionnel entre étapes) mais ses fondations le sont : kill switch (`cancel_mission`), `max_steps`, verrouillage anti-concurrence à deux sessions PostgreSQL vérifié réel. Niveau 4 non livré, hors scope. Correlation Agent et Report Agent livrés, tous deux strictement en lecture seule (aucun accès `Session`, vérifié statiquement) — voir [phase-18-ai-agents.md](phase-18-ai-agents.md) pour l'architecture complète, l'audit de sécurité, et la vérification en conditions réelles (Docker + navigateur + Ollama réel).

### Phase 19 — Mémoire IA par Projet/Asset

**Objectif** : reprendre l'idée de mémoire du brouillon (section 11), déjà partiellement possible puisque Project/Target existent depuis la Phase 11.

- Résumés automatiques stockés (pas recalculés à chaque question) : un job planifié (Phase 14) génère un résumé "état du projet" après chaque batch de scans, stocké comme un `Finding` de type `SUMMARY` ou une table dédiée `project_ai_summary`.
- Questions temporelles ("qu'est-ce qui a changé depuis le dernier audit ?") : rendues possibles directement par le Diff Engine de la Phase 14 — la mémoire IA n'est qu'une couche de présentation en langage naturel par-dessus des données déjà structurées, pas un nouveau système de stockage.

**Complexité** : S/M.

---

## 7. Track C — Workflow & Reporting

### Phase 20 — Evidence & Chain of Custody

Bonne idée du brouillon (section 12), déjà à moitié construite : chaque `Job` a déjà `stdout`/`stderr`/`result`/timestamps. Ce qui manque réellement :

- Un hash (SHA-256) du `stdout` brut calculé à la fin de chaque job, stocké — preuve d'intégrité minimale, pas de vault cryptographique complexe.
- Une timeline dédiée par Asset/Project qui n'est qu'une vue sur les `Job`/`Finding` déjà existants, triés chronologiquement — pas une nouvelle table `Evidence` dupliquant les données de `Job`.

**Complexité** : S.

### Phase 21 — Tool Orchestrator (chaînage de jobs)

Reprendre l'idée (section 15 du brouillon) mais en restant dans les limites du Policy Engine existant :

```text
nmap (quick_scan)
   ↓ (si port 80/443 ouvert détecté dans le résultat)
whatweb (basic_fingerprint)
   ↓ (si technologie identifiée)
nuclei (quick_scan, filtré sur les tags pertinents)
```

- Implémentation : une `MissionTemplate` = liste ordonnée de (tool, profile, condition sur le résultat précédent). Chaque étape reste un job normal créé via `POST /api/jobs` avec target_id — donc toujours soumis à l'authorization Target. Pas de nouveau moteur d'exécution, juste un déclenchement séquentiel côté worker existant.
- Conditions volontairement simples au départ (port ouvert détecté, techno détectée, sévérité minimale atteinte) plutôt qu'un DSL de branchement complet — étendre seulement si le besoin est prouvé par l'usage.

**Complexité** : M.

### Phase 22 — Reports 2.0 & Pentest Workspace

- Reprendre les formats du brouillon (Executive/Technical/Evidence Package) — réalistes, ce sont des templates Jinja2/reportlab supplémentaires sur le moteur de rapports déjà existant (Phase 9), pas une réécriture.
- "Pentest Workspace" (section 25 du brouillon) : déjà largement couvert par `Project` + tabs (Overview/Targets/Scans/Findings/Labs/AI/Reports, Phase 11) — ajouter un onglet "Notes" (texte libre par projet) et une timeline (Phase 20) suffit à couvrir le besoin réel, pas un module séparé.

**Complexité** : S/M.

---

## 8. Pistes à horizon plus lointain (gardées, mais reformulées)

Ces idées du brouillon original restent valables mais ne doivent être lancées qu'une fois les Tracks A/B/C ci-dessus livrés et *réellement utilisés* — sinon elles seront conçues sans les retours d'usage nécessaires :

- **Attack Path Analysis (léger)** : une fois le Security Graph (Phase 17) alimenté par de vraies données pendant plusieurs mois, ajouter des requêtes de chemins (`WITH RECURSIVE` sur `graph_edges`) présentées explicitement comme des **hypothèses à vérifier**, jamais des faits — reprend la mise en garde du brouillon original (section 38) qui est juste, et l'approche mesurée de FalconForce/BloodHound sur MITRE ATT&CK.
- **Mode SOC-lite** : pas une plateforme SOC complète (le brouillon V3 section 24/41/42 décrit littéralement un SIEM), mais une vue "Findings actifs + changements récents" déjà largement couverte par Dashboard (existant) + Diff Engine (Phase 14) + Risk Score (Phase 15). Ne construire un vrai module Incident/Investigation séparé que si un besoin concret apparaît.
- **Multi-Kali (opt-in)** : seulement si un utilisateur a réellement besoin de paralléliser des scans longs. Le faire en `docker-compose scale` d'abord (plusieurs conteneurs `cyberlab-kali` identiques derrière un `kali_agent_url` choisi par le worker selon la charge) avant d'imaginer un scheduler distribué complet — 90 % de la valeur pour 10 % du coût de la section 23 du brouillon.
- **Plugin System** : seulement une fois que 3-4 outils externes réels (Burp, Wireshark…) ont montré un besoin d'intégration récurrent — concevoir une API de plugin *avant* d'avoir un deuxième cas d'usage concret produit systématiquement une mauvaise abstraction.

---

## 9. Explicitement hors scope (et pourquoi)

Ces sections du brouillon original sont **volontairement écartées**, pas oubliées :

| Idée du brouillon | Pourquoi elle ne correspond pas à CyberLab aujourd'hui |
|---|---|
| Multi-Tenant / Organizations / Billing / Quotas (section 45) | CyberLab n'a même pas de deuxième utilisateur. Concevoir l'isolation multi-tenant sans un seul tenant réel pour la valider produirait une abstraction fausse. |
| SSO / Service accounts (section 45/46) | Suppose un système de comptes qui n'existe pas — voir la décision RBAC déjà documentée en Phase 11. |
| Event Bus généralisé (section 48) | Architecture microservices pour un outil qui tourne sur une seule machine avec 8 conteneurs. Redis pub/sub (déjà utilisé pour les statuts de job en temps réel) couvre le besoin réel actuel. |
| Distributed Execution / Worker Pool générique (section 22) | Un seul worker RQ n'a jamais été un goulot d'étranglement observé. Le "Multi-Kali opt-in" de la section 8 ci-dessus couvre le vrai besoin (paralléliser des scans) sans le coût d'un scheduler distribué. |
| CLI + SDK public + API publique versionnée comme produit (sections 46/47) | Prématuré tant que l'API interne elle-même change encore d'une phase à l'autre. Une vraie API publique implique un contrat de compatibilité que CyberLab n'a pas les moyens de maintenir à ce stade. |
| Advanced RBAC/ABAC entreprise (section 44) | Même raison que Multi-Tenant — pas d'identité utilisateur à qui attacher un rôle. |
| Digital Twin / Cyber Range Platform complet (sections 30/39/40) | Séduisant mais correspond à un produit entier (type RangeForce/Hack The Box Enterprise). Le Lab Factory existant (Phase 7, DVWA) couvre le besoin réel d'un utilisateur solo ; l'étendre à Windows/AD/Cloud est un projet à part entière, pas une case à cocher. |
| Benchmark Engine comme système séparé (section 33) | Utile en interne (déjà informellement fait via les tests de bout en bout à chaque phase), mais construire un moteur de benchmark comparant versions/modèles/pipelines suppose plusieurs déploiements en parallèle à comparer — pas le cas ici. |
| Auto-Remediation (section 31) | CyberLab n'a et ne doit avoir aucun mécanisme d'écriture sur une infrastructure cible, lab ou non — contraire au principe fondateur du projet (outil d'observation/scan, jamais de modification). À ne reconsidérer que si un jour un mode "lab d'apprentissage à la remédiation" isolé et clairement séparé du reste est explicitement demandé. |

---

## 10. Séquencement suggéré

```text
Phase 13  Asset Model                     ─┐
Phase 14  Continuous Recon + Diff          │  Track A, dans l'ordre
Phase 15  Risk Score (EPSS+CVSS+KEV)       │  (chaque phase dépend
Phase 16  Corrélation & dédup              │   de la précédente)
Phase 17  Security Graph                  ─┘

Phase 18  Agents spécialisés (IA)         ─┐  Track B — peut démarrer
Phase 19  Mémoire IA                       │  en parallèle de A après
                                           ─┘  la Phase 13

Phase 20  Evidence & Chain of Custody     ─┐  Track C — peut démarrer
Phase 21  Tool Orchestrator                │  en parallèle, indépendant
Phase 22  Reports 2.0 / Workspace         ─┘

Ensuite, seulement si l'usage le justifie :
  Attack Path · SOC-lite · Multi-Kali opt-in · Plugin System
```

---

## Sources

Recherches effectuées pour ancrer cette révision dans des pratiques réelles (2026) :

- [Vulnerability Prioritization in 2026: Why CVSS Isn't Enough — Picus Security](https://www.picussecurity.com/resource/blog/vulnerability-prioritization-why-cvss-isnt-enough)
- [How to Prioritize Vulnerabilities in 2026: From CVSS to Real Risk — Cymulate](https://cymulate.com/blog/how-to-prioritize-vulnerabilities/)
- [EPSS vs. CVSS: what's the best approach to vulnerability prioritization? — Intruder](https://www.intruder.io/blog/epss-vs-cvss)
- [open-asm — AI-powered open-source Attack Surface Management platform (GitHub)](https://github.com/oasm-platform/open-asm)
- [Open Source Attack Surface Management (ASM) Guide — SentinelOne](https://www.sentinelone.com/cybersecurity-101/cybersecurity/open-source-attack-surface-management/)
- [The 12 Best Agentic SOC Platforms in 2026 — Security Boulevard](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/)
- [AgentSOC: A Multi-Layer Agentic AI Framework for Security Operations Automation (arXiv)](https://arxiv.org/html/2604.20134)
- [Graphs for cybersecurity: Knowledge Graph as digital twin — Neo4j](https://neo4j.com/blog/security/graphs-cybersecurity-knowledge-graph-digital-twin/)
- [Graphing MITRE ATT&CK via Bloodhound — FalconForce](https://falconforce.nl/graphing-mitre-attck-via-bloodhound/)
- [ATHAFI: Agile Threat Hunting And Forensic Investigation (BRON graph, arXiv)](https://arxiv.org/pdf/2003.03663)
- [NVD Vulnerability APIs — NIST](https://nvd.nist.gov/developers/vulnerabilities)
- [OpenCVE — Self-hosted Vulnerability Intelligence Platform](https://www.opencve.io/)

Sources internes au projet référencées : `docs/security.md`, `docs/tools.md`, `docs/architecture.md`, `CHANGELOG.md`.
