# Findings & Reports

## Findings

Un `Finding` normalise le résultat d'un outil en un modèle commun : `job_id`, `target`, `source_tool`, `title`, `description`, `severity`, `confidence`, `evidence` (JSON brut de l'outil), `recommendation`.

### Extraction automatique (`backend/app/findings/extractor.py`)

Dès qu'un job passe à `SUCCESS`, `execute_job()` appelle `extract_findings(tool, target, parsed_result)` et persiste les findings produits — aucune action manuelle. Un extracteur par outil, volontairement conservateur sur la sévérité (jamais `HIGH`/`CRITICAL` depuis une simple heuristique, sans vérification) :

| Outil | Logique | Sévérité |
|---|---|---|
| nmap | Un finding par port **ouvert** (les ports fermés/filtrés sont ignorés) | `LOW` pour les services en clair historiquement risqués (ftp, telnet, rsh, rlogin, vnc), `INFO` sinon |
| whatweb | Un finding par plugin/technologie détecté | `INFO` toujours |
| nikto | Un finding par ligne de résultat | `MEDIUM` si le texte contient un mot-clé de vulnérabilité (XSS, injection, OSVDB, disclosure...), `LOW` sinon |

### API

- `GET /api/findings?severity=&job_id=&limit=`
- `GET /api/findings/{id}`

## Reports

Un `Report` agrège un ensemble de jobs (+ leurs findings + leur analyse IA si présente) en un document exportable, persisté en base (`backend/app/models/report.py`) — regénérable/téléchargeable sans recalcul.

### Génération (`backend/app/reports/`)

```
builder.py            — assemble jobs + findings + ai_analysis en un dict commun
renderers/
  json_renderer.py     — json.dumps
  markdown_renderer.py — Markdown structuré (Executive Summary, Scope, Findings, Timeline)
  html_renderer.py     — template Jinja2, thème clair pensé pour l'impression/le partage
  pdf_renderer.py       — reportlab (pur Python, pas de dépendance système comme Cairo/Pango)
```

Contenu (conforme à la spec) : Executive Summary, Scope (cibles + outils utilisés), Findings (avec preuve/`evidence`), Timeline, Analyse IA par job. Les formats binaires (PDF) sont stockés encodés en base64 dans la colonne texte `Report.content`.

### API

- `POST /api/reports` `{title, job_ids, format}` → `201` avec les métadonnées.
- `GET /api/reports` / `GET /api/reports/{id}` — métadonnées.
- `GET /api/reports/{id}/download` — contenu avec `Content-Type` et `Content-Disposition: attachment` corrects.

## Bug réel trouvé et corrigé en Phase 9 : `created_at` figé

`server_default="now()"` (chaîne Python brute) sur `Job`/`Finding`/`Report` était compilé par SQLAlchemy en littéral SQL `DEFAULT 'now()'` — Postgres évalue ce cast **une seule fois, à la création de la table**, et réutilise ensuite cette même valeur figée pour chaque ligne insérée. Toutes les lignes d'une table partageaient donc le même `created_at`, jusqu'à la prochaine migration recréant la table. Corrigé avec `sa.text("now()")` (appel de fonction SQL non quoté, réévalué à chaque insertion) + migration `6ad0daaf9daa` corrigeant les colonnes déjà en place. Repéré en observant des timestamps identiques sur des rapports générés à plusieurs minutes d'écart.
