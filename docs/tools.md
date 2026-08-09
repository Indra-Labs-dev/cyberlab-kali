# Tool Registry

Chaque outil Kali est décrit par un fichier YAML déclaratif dans `backend/app/tools/definitions/`, jamais codé en dur côté frontend ni dans les routes API.

## Format d'une définition

```yaml
name: nmap
category: reconnaissance
command:
  executable: nmap
fixed_args: ["-oX", "-", "-sT"]   # toujours appliqués (ex : force une sortie parseable)
arguments:
  - name: target
    type: target        # target | url | string | boolean | choice | integer
    required: true
    positional: true    # place la valeur en fin de commande plutôt qu'après un flag
  - name: service_detection
    type: boolean
    flag: "-sV"
    default: false
output:
  format: xml
  parser: nmap
```

## Validation (`backend/app/tools/registry.py`)

`build_command(tool_name, params)` transforme un dict de paramètres utilisateur en liste d'arguments prête à être envoyée à l'agent Kali (jamais une chaîne shell). Contrôles appliqués :

- **Allowlist** : seuls les outils ayant un fichier de définition sont exécutables (`ToolNotFoundError` sinon).
- **Arguments inconnus rejetés** (`ToolValidationError`).
- **`target`** : hostname/IP/CIDR, rejette tout ce qui commence par `-` (anti flag-injection) et les métacaractères shell.
- **`url`** : comme `target`, mais accepte un préfixe `http://`/`https://` (pour whatweb/nikto).
- **`string`** : motif par défaut restrictif, ou `pattern` personnalisé défini dans le YAML (ex. la liste de ports de nmap).
- **`choice`** : valeur dans une liste fermée (ex. `-T` de nmap limité à `1..4`, `5` explicitement exclu car trop agressif).
- **`boolean`** / **`integer`** : type strict, bornes `min_value`/`max_value` pour les entiers.

Cette validation est une couche supplémentaire **avant** l'agent Kali, qui revalide indépendamment (voir [security.md](security.md)) — défense en profondeur.

## Sortie / parsers (`backend/app/tools/parsers/`)

| Outil | Format brut | Parser | Sortie normalisée |
|---|---|---|---|
| nmap | XML (`-oX -`), parsé avec `defusedxml` (anti-XXE) | `parsers/nmap.py` | `{"hosts": [{"address", "hostname", "state", "ports": [...]}]}` |
| whatweb | JSON (`--log-json=-`) | `parsers/whatweb.py` | `{"results": [...]}` |
| nikto | texte (`-Format txt`) | `parsers/nikto.py` | `{"target_ip", "target_hostname", "findings": [...]}` |

## API

- `GET /api/tools` — liste les définitions disponibles.
- `GET /api/tools/{name}` — détail d'un outil (404 si inconnu).

L'exécution effective (Job Engine) est branchée en Phase 4 via `backend/app/jobs/tasks.py::run_registered_tool_job`, qui valide via le registre, appelle l'agent Kali, puis parse la sortie.

## Ajouter un nouvel outil

1. Créer `backend/app/tools/definitions/<outil>.yaml`.
2. Ajouter l'exécutable à l'allowlist de `kali/agent/main.py` (`ALLOWED_TOOLS`) et l'installer dans `kali/Dockerfile`.
3. Écrire un parser dans `backend/app/tools/parsers/` et l'enregistrer dans `parsers/__init__.py`.
4. Ajouter des tests dans `backend/tests/tools/`.
