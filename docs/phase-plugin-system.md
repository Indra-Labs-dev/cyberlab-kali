# Plugin System (opt-in) — répertoire externe de définitions d'outils

## Périmètre exact (override explicite)

Texte de la roadmap (`docs/roadmap.md`, §8) : « seulement une fois que 3-4 outils externes réels (Burp, Wireshark…) ont montré un besoin d'intégration récurrent — concevoir une API de plugin *avant* d'avoir un deuxième cas d'usage concret produit systématiquement une mauvaise abstraction. »

Aucun de ces cas d'usage n'existe réellement (ni Burp ni Wireshark n'a jamais été intégré à CyberLab). Cette piste a néanmoins été lancée par le même override explicite que SOC-lite et Multi-Kali (voir §7quater). La mise en garde de la roadmap contre la « mauvaise abstraction » est prise au sérieux : plutôt que d'inventer une API de plugin générique pour des intégrations hypothétiques, cette implémentation **généralise le mécanisme existant** (Tool Registry YAML + allowlist Kali) à un second répertoire, contrôlé par l'opérateur, sans toucher à son architecture d'exécution.

## Constat de l'inspection read-only préalable

- Chaque outil est déjà défini par un fichier YAML (`backend/app/tools/definitions/*.yaml`), validé par le schéma Pydantic `ToolDefinition` (`backend/app/tools/schema.py`), chargé une fois via `_load_definitions()` (`@lru_cache`).
- L'exécution ne passe **jamais** par autre chose qu'un `subprocess.run` à l'intérieur du conteneur Kali (`POST /exec` sur `kali/agent/main.py`) — aucun chemin HTTP-vers-service-externe n'existe nulle part dans le code.
- Chaque outil nécessite un **double enregistrement** : une fois côté API (YAML) et une fois côté agent Kali (`CANDIDATE_TOOLS` dans `kali/agent/main.py`), l'exécutable devant être résolvable via `shutil.which()` dans l'image du conteneur.
- `docs/tools.md` documente déjà une philosophie de **liste curatée, pas de marketplace** (hydra/john/hashcat/lynis/jq explicitement exclus alors qu'installés) — cette piste ne change pas cette philosophie, elle ajoute juste une seconde source de définitions, elle-même curatée par l'opérateur qui la configure.
- Burp et Wireshark ne sont structurellement **pas** des binaires CLI invocables par sous-processus avec un modèle "une cible, un run" — les intégrer nécessiterait un tout nouveau transport HTTP-vers-service-externe. Construire ce transport sans un seul besoin concret serait exactement la « mauvaise abstraction » que le texte de la roadmap met en garde contre, et violerait la contrainte explicite de l'utilisateur (« pas de refonte inutile de l'architecture », « pas d'infrastructure ajoutée uniquement au cas où »).

## Décision de périmètre

Le plus petit périmètre honnête retenu : un **second répertoire de définitions YAML**, optionnel, configuré par l'opérateur (`TOOL_DEFINITIONS_EXTRA_DIR`), rechargé par le même `_load_definitions()`, réutilisant à 100 % :
- le schéma `ToolDefinition` (mêmes règles, y compris `MANUAL_ONLY` ⇒ `ai_allowed: false`) ;
- `_validate_definition_integrity()` (mêmes contraintes structurelles) ;
- le Policy Engine / filtrage `ai_allowed` / `is_executable()` (aucun code ne distingue l'origine d'une définition) ;
- le pipeline d'exécution existant (toujours `subprocess` dans le conteneur Kali, jamais autre chose).

Côté agent Kali, le pendant symétrique : `EXTRA_ALLOWED_TOOLS` (variable d'environnement, format `nom1:executable1,nom2:executable2`), fusionné avec `CANDIDATE_TOOLS` avant la même résolution `shutil.which()` que les outils curatés — un nom listé ici ne devient exécutable que si le binaire est réellement présent dans l'image (ex. une image Kali étendue par l'opérateur via son propre `Dockerfile`).

**Explicitement non couvert, documenté ici plutôt que sur-promis** : intégration Burp/Wireshark/tout service externe non-CLI. Ce périmètre reste un mécanisme de plugin pour des **binaires CLI supplémentaires**, pas un marketplace public, pas un nouveau transport d'exécution.

## Changements

### Backend

- `app/core/config.py` — `tool_definitions_extra_dir: str` (défaut `""`, `TOOL_DEFINITIONS_EXTRA_DIR`), même forme "raw string" que `cors_origins_raw`/`kali_agent_urls_raw`.
- `app/tools/registry.py` — `_load_definitions()` étendu : après le chargement (toujours strict) des définitions intégrées, un second passage optionnel scanne `tool_definitions_extra_dir` :
  - un fichier YAML malformé ou invalide est **isolé** (loggé, ignoré) — jamais fatal pour les 31 outils curatés ni pour les autres fichiers externes valides ;
  - un nom en collision avec un outil intégré est **rejeté loudly** (loggé en erreur, ignoré) — jamais de shadowing silencieux d'un outil curaté.

### Agent Kali

- `kali/agent/main.py` — `_parse_extra_tools(raw, existing)` : parse `EXTRA_ALLOWED_TOOLS`, ignore les entrées malformées (pas de `:`, nom/exécutable vide) et les collisions avec `CANDIDATE_TOOLS`, sans jamais lever d'exception (un typo opérateur ne doit pas empêcher l'agent de démarrer). Le résultat (`EXTRA_CANDIDATE_TOOLS`) est fusionné avec `CANDIDATE_TOOLS` avant la résolution `shutil.which()` déjà existante — un nom listé ne devient réellement exécutable que si le binaire existe dans l'image.

### Documentation

- `docs/roadmap.md` (§7quater, §8) — statut mis à jour.
- `docs/security.md` — nouvelle section d'audit (voir ci-dessous).

## Tests

- `backend/tests/tools/test_plugin_registry.py` (6 tests, réel filesystem/YAML, pas de mock) : comportement inchangé quand `tool_definitions_extra_dir` est vide ou pointe vers un répertoire inexistant ; un outil externe valide se charge et fonctionne via le même `build_command()` que les outils intégrés ; un fichier externe malformé est isolé sans casser les 31 outils curatés ni les autres fichiers externes valides ; une collision de nom avec un outil intégré (`nmap`) est rejetée, l'outil intégré restant intact ; la règle `MANUAL_ONLY` ⇒ `ai_allowed: false` s'applique identiquement à un outil chargé en externe (aucun cas particulier par origine).
- `kali/agent/tests/test_plugin_tools.py` (9 tests) : `_parse_extra_tools()` — entrée vide, entrée simple, entrées multiples, espaces autour des séparateurs, entrée sans `:` ignorée, nom/exécutable vide ignoré, entrées vides entre virgules ignorées, collision avec un outil curaté rejetée, seuls les binaires réellement résolvables via `shutil.which()` finissent autorisés.
- Régression complète : `backend/tests/tools/` 43/43 (37 pré-existants + 6 nouveaux) ; `kali/agent/tests/` 22/22 (13 pré-existants + 9 nouveaux).

## Vérification en conditions réelles (Docker E2E)

Les deux images (`cyberlab-api`, `cyberlab-kali`) ont été reconstruites pour embarquer le code de cette piste (le code n'est pas monté en volume — voir `docs/development.md`). Un conteneur Kali ad-hoc (`docker run`, copie exacte de la posture de sécurité de `cyberlab-kali` : `cap_drop: ALL`, `cap_add: [NET_RAW]`, `no-new-privileges`, non-root, réseau `cyberlab-kali-net` uniquement) a été démarré avec `EXTRA_ALLOWED_TOOLS=echotest:echo` :

1. `GET /health` sur ce conteneur confirme `echotest` dans `tools_available`, aux côtés des 31 outils curatés.
2. Appel réel `POST /exec` (`{"tool": "echotest", "args": ["hello-plugin-e2e"]}`) exécute un vrai sous-processus et retourne `hello-plugin-e2e` en stdout.
3. Depuis le conteneur `cyberlab-api` réel, avec `TOOL_DEFINITIONS_EXTRA_DIR` pointant vers un fichier YAML écrit sur le disque du conteneur : `registry.get_tool("echotest")` charge la définition externe, `registry.build_command()` produit les arguments validés via le même pipeline que les outils intégrés, et `app.jobs.kali_client.run_tool()` dispatche réellement vers le conteneur Kali ad-hoc par HTTP — retour confirmé : `{"exit_code": 0, "stdout": "hello-from-backend-plugin-e2e\n", ...}`.

Aucune donnée fictive persistée, aucun fichier suivi par git modifié pendant la vérification. Le conteneur ad-hoc et les fichiers temporaires ont été supprimés après le test ; la stack a été laissée dans son état par défaut (images reconstruites avec le code final de cette piste, ce qui est le résultat attendu).

## Limites assumées

- Toujours pas de marketplace, pas de découverte automatique, pas de signature/vérification cryptographique des définitions externes — l'opérateur qui configure `TOOL_DEFINITIONS_EXTRA_DIR` est réputé de confiance (même modèle que l'opérateur qui étend l'image Kali elle-même).
- Toujours aucun chemin d'exécution autre que `subprocess` dans le conteneur Kali — Burp/Wireshark/tout service HTTP externe restent hors périmètre, faute de besoin concret démontré.
- Le parseur de sortie (`app/tools/parsers/__init__.py::PARSERS`) reste un dict Python codé en dur, non extensible depuis un plugin externe — un outil externe doit utiliser `format: text` avec `parser: none` (ou un parser déjà existant) ; ajouter un parser reste un changement de code, volontairement non couvert par cette piste (aucun besoin concret ne l'a justifié).
