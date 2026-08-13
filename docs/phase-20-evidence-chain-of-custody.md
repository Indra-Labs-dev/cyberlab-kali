# Phase 20 — Evidence & Chain of Custody

Livraison réelle de la Phase 20 planifiée dans [roadmap.md](roadmap.md#phase-20--evidence--chain-of-custody). Deux livrables, tous deux volontairement minimaux ("preuve d'intégrité minimale, pas de vault cryptographique complexe") :

1. **Hash SHA-256 du `stdout`** de chaque `Job`, calculé et stocké à la fin de son exécution.
2. **Timeline Evidence** par Asset/Project — une vue chronologique fusionnée sur `Job`/`Finding` déjà existants, **pas** une nouvelle table.

## Décisions architecturales (divergences documentées)

1. **Calcul inline, pas un hook isolé comme Mission/Mémoire (Phase 18/19)** — ces deux hooks sont isolés (session séparée, `finally` le plus externe d'`execute_job()`) précisément parce qu'ils font un appel réseau/LLM lent. Un SHA-256 sur du texte déjà en mémoire est local, synchrone, instantané — il reste dans la même transaction que `exit_code`/`result`, exactement à l'endroit où `stdout` lui-même est déjà écrit (`app/jobs/tasks.py::_execute_job`).
2. **Hash calculé pour tout job qui a produit un `stdout`, pas seulement les `SUCCESS`** — la roadmap dit "à la fin de chaque job" ; un job `FAILED` par code de sortie non nul a quand même produit une sortie réelle qui mérite une preuve d'intégrité. Seuls les deux chemins d'exception (`ToolNotFoundError`/`ToolValidationError`/`KaliAgentError`, exception inattendue) laissent le hash `NULL`, puisque l'outil n'a alors jamais tourné — il n'y a rien dont prouver l'intégrité.
3. **Un `stdout` vide obtient quand même un hash bien défini** (celui de la chaîne vide), jamais confondu avec `NULL` — `NULL` signifie "aucune sortie n'a jamais existé", pas "la sortie était vide".
4. **Timeline = fusion Job + Finding uniquement**, jamais `AssetChangeEvent` — la roadmap est explicite ("une vue sur les Job/Finding déjà existants"). `AssetChangeTimeline.vue` (Phase 14, déjà livré) reste intact et non modifié ; la nouvelle Evidence Timeline est un composant séparé, pas une fusion avec un composant d'une phase précédente déjà gelée.
5. **Composant partagé, pas dupliqué** — `EvidenceTimeline.vue` est un composant purement présentationnel (props `jobs`/`findings`, ne fait aucun appel réseau lui-même) réutilisé à la fois sur la page Asset (nouvelle section) et sur la page Project (nouvel onglet `timeline`) — la logique de fusion/tri chronologique n'existe qu'une fois.
6. **Bug préexistant trouvé et corrigé en cours de route** (sans rapport avec Phase 20, découvert en testant `EvidenceTimeline.vue` en isolation) : `JobStatusBadge.vue` utilisait `computed()` sans l'importer explicitement — fonctionnait dans l'app Nuxt réelle (auto-import), mais plantait dans n'importe quel test Vitest simple qui le montait pour la première fois. Corrigé par un simple `import { computed } from "vue"`, même classe de correction déjà appliquée aux badges de la Phase 18.

## Architecture

```text
app/models/job.py            — Job.evidence_sha256 (String(64), nullable), migration b2d5f8a1c6e3
app/jobs/tasks.py             — hashlib.sha256(job.stdout.encode()).hexdigest(), même transaction
app/schemas/job.py             — JobResponse.evidence_sha256 (un seul champ, aucune nouvelle route)

frontend/app/components/EvidenceTimeline.vue — fusion Job+Finding, triée chronologiquement
  - Job : timestamp = finished_at ?? created_at
  - Finding : timestamp = first_seen
  utilisé sur pages/assets/[id].vue (nouvelle section) et pages/projects/[id].vue (nouvel onglet)
pages/scans/[id].vue           — hash affiché à côté de stdout, bouton copier
```

Aucune nouvelle route API : `evidence_sha256` apparaît automatiquement sur `GET /api/jobs`, `GET /api/jobs/{id}`, et dans le payload que le frontend reçoit déjà — un seul champ de schéma ajouté (`app/schemas/job.py`).

## Vérification réelle (Docker + navigateur + PostgreSQL)

Conteneurs `cyberlab-api`/`cyberlab-worker`/`cyberlab-frontend` reconstruits et redémarrés, migration `b2d5f8a1c6e3` appliquée (upgrade → downgrade → upgrade vérifié contre la vraie base de dev, backup réel pris avant).

Sur l'Asset DVWA E2E réel :
1. Scan `whatweb` réel lancé depuis l'UI → `SUCCESS` → hash affiché sur la page Scan (`sha256:3fbbd4c6d761…`).
2. **Hash recalculé indépendamment côté PostgreSQL** (`encode(sha256(stdout::bytea), 'hex')`) — **correspondance exacte** avec `evidence_sha256` stocké, preuve cryptographique que le hash est correct, pas un artefact d'affichage.
3. Evidence Timeline vérifiée sur la page Asset (nouvelle section, en bas, après les sections existantes intactes) et sur la page Project (nouvel onglet `timeline`) — les deux affichent le même job le plus récent en tête, avec son hash tronqué, correctement entrelacé avec les Findings par ordre chronologique.
4. Un job `amass` antérieur à cette phase, sans hash (créé avant le déploiement du calcul de hash) — comportement attendu, pas une régression : le hash n'est jamais calculé rétroactivement pour l'historique existant.
5. Logs du worker : une régénération de résumé IA (Phase 19) a échoué pendant ce test (`OllamaUnavailableError`, Ollama momentanément injoignable) — le job `execute_job()` a quand même terminé avec succès ("Job OK"), confirmation en conditions réelles (pas seulement en test) que l'isolation Phase 19 fonctionne : une panne dans un hook post-completion ne peut jamais faire échouer le Job lui-même. Sans rapport avec Phase 20.

## Tests

11 nouveaux tests backend (497 au total) : hash correct sur succès, hash calculé même sur code de sortie non nul, hash bien défini (pas `NULL`) pour un stdout vide, hash `NULL` quand l'outil n'a jamais tourné (deux chemins d'exception distincts testés). 6 nouveaux tests frontend (101 au total) : rendu job/finding, troncature du hash, absence de ligne hash quand `evidence_sha256` est `null`, tri chronologique, repli sur `created_at` pour un job encore `RUNNING`.

## Ce qui n'est délibérément pas fait

- Pas de vault cryptographique, pas de signature, pas de chaînage de hash (blockchain-style).
- Pas de nouvelle table `Evidence` — explicitement exclu par la roadmap.
- Pas de fusion avec `AssetChangeEvent`/`AssetChangeTimeline.vue` — hors périmètre littéral, composant d'une phase précédente non retouché.
- Aucune interaction avec `app/reports/builder.py` (Phase 22 "Reports 2.0") — le générateur de rapport n'exposait déjà pas `stdout`, rien à modifier.
- Aucun recalcul rétroactif du hash pour les jobs déjà terminés avant cette phase.
