# Tool Registry

Chaque outil Kali est décrit par un fichier YAML déclaratif dans `backend/app/tools/definitions/`, jamais codé en dur côté frontend ni dans les routes API. Depuis la Phase 12, le registre couvre 31 outils réels et testés (voir le [CyberLab Tool Arsenal](#cyberlab-tool-arsenal) ci-dessous), organisés en profils curés plutôt qu'en arguments CLI bruts.

## Architecture

```
Kali tools
 ↓
Tool Registry (YAML + schema.py)      -- discovery, définitions, profils
 ↓
Validation (registry.py)              -- types, patterns, allowlist d'arguments
 ↓
Policy Engine (jobs.py + authorization.py)  -- autorisation de la Target, ai_allowed
 ↓
Job Engine (tasks.py)                 -- exécution, parsing, extraction de findings
 ↓
Agent Kali (kali/agent/main.py)       -- allowlist d'exécutables, subprocess(shell=False)
```

Seuls les outils explicitement déclarés dans le Registry **et** dans l'allowlist de l'agent Kali (`CANDIDATE_TOOLS` dans `kali/agent/main.py`) peuvent être exécutés via l'API ou l'IA. Le Terminal (`/terminal`) reste entièrement séparé de cette architecture — un shell complet, sans allowlist, confiné au conteneur Kali (voir [security.md](security.md)).

## Format d'une définition

```yaml
name: nmap
category: reconnaissance
description: Network exploration and port/service scanning.
risk_level: CAUTION          # SAFE | CAUTION | RESTRICTED | MANUAL_ONLY
ai_allowed: true              # si false, l'IA ne voit même pas ce nom dans son prompt
command:
  executable: nmap
fixed_args: ["-oX", "-", "-sT", "-Pn"]
arguments:
  - name: target
    type: target              # target | url | string | boolean | choice | integer
    required: true
    positional: true
  - name: service_detection
    type: boolean
    flag: "-sV"
    default: false
output:
  format: xml
  parser: nmap                 # "none" si l'outil n'a pas de parser structuré
profiles:
  - name: quick_scan
    description: "Fast top-ports scan, no service/version probing."
    args: {timing: "4", top_ports: 100}
    timeout: 60
    risk_level: null            # optionnel, override le risk_level du tool pour ce profil
```

## Profils : la couche UX au-dessus de la validation existante

Un **profil** est un préréglage nommé de valeurs d'arguments (`args`), pensé pour l'interface et le Mission Planner IA — jamais un second niveau de confiance. `build_command(tool, params, profile=...)` fusionne `profile.args` comme valeurs par défaut, que `params` (les options explicitement fournies) peut toujours surcharger clé par clé ; **toutes** les valeurs, qu'elles viennent du profil ou de `params`, passent par exactement la même validation par type/pattern que le mode "arguments bruts". Un profil ne peut donc jamais faire passer une valeur que `build_command` aurait autrement rejetée — voir `backend/app/tools/registry.py::_validate_definition_integrity` et `build_command`.

Contraintes vérifiées au chargement (`registry.py`) :

- Chaque profil référence uniquement des arguments réellement déclarés sur l'outil.
- Un profil ne peut jamais préréglé l'argument `target`/`url` — la cible vient toujours du job (`target_id` ou `target`), jamais d'un profil.
- Au plus deux arguments positionnels par outil (le premier doit être `target`/`url`/`string` ; le second existe pour les CLI à deux valeurs nues comme `nc host port`).

## Risk levels

- **SAFE** : passif/lecture seule, ne perturbe pas la cible (ex. bannière, lookup DNS).
- **CAUTION** : sondage actif, généralement acceptable en lab/cible autorisée mais peut être bruyant ou déclencher un IDS.
- **RESTRICTED** : envoie beaucoup de requêtes ou peut stresser un service fragile (scan de vulnérabilités actif).
- **MANUAL_ONLY** : implique toujours `ai_allowed: false` (imposé par un validateur pydantic, `schema.py`). Ne signifie pas "personne ne peut l'utiliser" — un humain peut toujours le lancer via la page Tools ; seule l'IA ne peut jamais l'atteindre.

## `ai_allowed` — appliqué, pas seulement affiché

Le Mission Planner IA (`backend/app/ai/planner.py`) filtre `ai_allowed=False` **avant même de construire le prompt** — le modèle n'est jamais informé qu'un tel outil existe. Défense en profondeur : même si le modèle propose quand même un nom réel (`"sqlmap"`, appris de ses données d'entraînement plutôt que du prompt), l'étape est revalidée après coup contre le même filtre et son `tool` est mis à `null`. Un nom de profil halluciné ou invalide subit le même traitement (`step.profile = None`) plutôt que d'être transmis tel quel. Voir `backend/tests/ai/test_ai_security_boundary.py`.

## Sortie / parsers (`backend/app/tools/parsers/`)

9 outils ont un parser structuré ; les 22 autres exposent leur sortie brute (`parser: none`), explicitement marquée comme telle plutôt que simulée (autorisé par conception — un outil sans parser reste utilisable, juste pas normalisé).

| Outil | Format brut | Sortie normalisée |
|---|---|---|
| nmap | XML (anti-XXE via `defusedxml`) | `{"hosts": [{"address","hostname","state","ports":[...]}]}` |
| whatweb | JSON | `{"results": [...]}` |
| nikto | texte | `{"target_ip","target_hostname","findings":[...]}` |
| masscan | JSON (réparation best-effort si tronqué par un timeout) | `{"hosts": [{"address","ports":[...]}]}` |
| gobuster | texte (regex sur les lignes `path (Status: N) [Size: N]`) | `{"results": [{"path","status","size"}]}` |
| nuclei | JSONL | `{"findings": [{"template_id","name","severity","matched_at","description"}]}` |
| sslscan | XML | `{"targets": [{"host","port","protocols","accepted_ciphers","certificate"}]}` |
| searchsploit | JSON (`-j`) | `{"exploits": [{"title","path","edb_id","date","type"}]}` |

Puis : `NormalizedResult → FindingExtractor → Findings` (`backend/app/findings/extractor.py`), avec la même sévérité conservatrice qu'en Phase 9 — sauf pour **nuclei**, seul extracteur qui fait confiance à la sévérité déjà attribuée par le template (revue communautaire), pas une heuristique CyberLab.

## CyberLab Tool Arsenal

31 outils, 9 catégories. Généré depuis le Registry réel (`registry.list_tools()`), pas une liste à jour manuellement.

| Catégorie | Outil | Objectif | Installé | Risk | AI | Profils | Parser |
|---|---|---|---|---|---|---|---|
| Reconnaissance | nmap | Découverte réseau, scan de ports/services | Oui | CAUTION | Oui | quick_scan, service_detection, top_ports, full_tcp, vulnerability_nse | nmap |
| Reconnaissance | masscan | Scan de ports haute vitesse (SYN brut, `CAP_NET_RAW`) | Oui | RESTRICTED | Oui | quick_scan | masscan |
| Reconnaissance | arp-scan | Découverte d'hôtes ARP (segment L2 local uniquement) | Oui | CAUTION | Oui | local_subnet_scan | none |
| Reconnaissance | netdiscover | Reconnaissance ARP active (segment L2 local) | Oui | CAUTION | Oui | local_subnet_scan | none |
| DNS/Network | dig | Requêtes DNS (A/MX/TXT/NS) | Oui | SAFE | Oui | standard_lookup, mx_lookup, txt_lookup, ns_lookup | none |
| DNS/Network | host | Résolution DNS simple | Oui | SAFE | Oui | default_lookup | none |
| DNS/Network | nslookup | Requête DNS (mode non-interactif) | Oui | SAFE | Oui | default_lookup | none |
| DNS/Network | whois | Enregistrement domaine/IP | Oui | SAFE | Oui | default_lookup | none |
| DNS/Network | traceroute | Traçage de route réseau | Oui | CAUTION | Oui | default_trace | none |
| DNS/Network | nc | Vérification de connectivité/bannière (netcat-openbsd, sans `-e`) | Oui | CAUTION | Oui | port_check | none |
| Web Recon | whatweb | Fingerprinting de technologies web | Oui | SAFE | Oui | basic_fingerprint, aggressive_fingerprint, verbose_fingerprint | whatweb |
| Web Recon | wafw00f | Détection de WAF | Oui | SAFE | Oui | detect_waf, detect_all | none |
| Web Recon | gobuster | Enumération de répertoires/fichiers (mode `dir`) | Oui | CAUTION | Oui | directory_enum_small, directory_enum_common, directory_enum_extensions | gobuster |
| Web Recon | ffuf | Fuzzing web (répertoires/paramètres) | Oui | CAUTION | Oui | directory_discovery, parameter_discovery | none |
| Web Security | nikto | Scanner de vulnérabilités web | Oui | RESTRICTED | Oui | basic_web_scan, tuning_scan | nikto |
| Web Security | nuclei | Scanner de vulnérabilités piloté par templates | Oui | RESTRICTED | Oui | quick_scan, critical_only | nuclei |
| Web Security | sqlmap | Détection/exploitation d'injection SQL (surface volontairement bornée) | Oui | **MANUAL_ONLY** | **Non** | detect_only, enumerate_databases | none |
| SSL/TLS | sslscan | Scan de configuration TLS/ciphers | Oui | SAFE | Oui | full_scan | sslscan |
| SSL/TLS | testssl | Vérification TLS/vulnérabilités élargie (`--fast`) | Oui | CAUTION | Oui | quick_check, vulnerability_check | none |
| Enumeration | enum4linux | Enumération SMB/Samba/Windows | Oui | CAUTION | Oui | basic_enum | none |
| Enumeration | smbclient | Listage de partages SMB (session anonyme) | Oui | SAFE | Oui | list_shares | none |
| Enumeration | rpcclient | Requête MS-RPC unique (sous-commandes allowlistées) | Oui | CAUTION | Oui | server_info, enum_users, enum_groups | none |
| Enumeration | ldapsearch | Requête LDAP anonyme (root DSE) | Oui | SAFE | Oui | rootdse_query | none |
| Vulnerability | searchsploit | Recherche locale Exploit-DB (hors-ligne) | Oui | SAFE | Oui | keyword_search | searchsploit |
| OSINT | theharvester | Harvesting passif (sous-domaines/hôtes) | Oui | SAFE | Oui | passive_recon | none |
| OSINT | amass | Enumération passive de sous-domaines | Oui | SAFE | Oui | passive_enum | none |
| OSINT | subfinder | Enumération passive rapide de sous-domaines | Oui | SAFE | Oui | passive_enum | none |
| OSINT | dnsrecon | Enumération DNS (sweep standard ou tentative AXFR) | Oui | CAUTION | Oui | standard_enum, zone_transfer_check | none |
| Utilities | curl | Requêtes HTTP(S) (GET uniquement) | Oui | SAFE | Oui | fetch_headers, fetch_body | none |
| Utilities | wget | Vérification de disponibilité (mode spider, aucun téléchargement) | Oui | SAFE | Oui | check_availability | none |
| Utilities | openssl | Inspection de certificat TLS (`s_client`) | Oui | SAFE | Oui | cert_info | none |

## Décisions documentées : ce qui n'est PAS dans le Registry

- **hydra, john, hashcat** : présents dans les dépôts Kali, **non installés**. `john`/`hashcat` opèrent sur des fichiers de hash hors-ligne, sans notion de cible réseau — aucun ajustement naturel au modèle `target_id` du Job Engine. `hydra` est un risque d'amplification par force brute réel, même contre une cible LAB (peut saturer/verrouiller un service bien plus agressivement qu'un scan). Décision différée, pas un oubli.
- **lynis** : installé (petit paquet, utile en Terminal), **non enregistré** dans le Registry. Lynis audite le système sur lequel il tourne, pas une cible réseau — le lancer "contre" une Target ne ferait qu'auto-auditer le conteneur `cyberlab-kali` lui-même, ce qui n'a pas de sens dans ce modèle.
- **jq** : installé, **non enregistré**. jq traite du JSON via stdin — aucune notion de cible, et aucun mécanisme de chaînage inter-jobs n'existe dans cette architecture pour lui fournir une entrée.

Les trois restent utilisables manuellement via le Terminal, qui est délibérément séparé et non restreint (voir [security.md](security.md)).

## API

- `GET /api/tools` — liste les définitions disponibles (avec `profiles`, `ai_allowed`).
- `GET /api/tools/{name}` — détail d'un outil (404 si inconnu).
- `GET /api/tools/health` — vérification non destructive par outil (`--version`/`--help`, jamais un vrai scan) : `ready` / `broken` / `not_installed` / `unknown` (agent injoignable). Voir la section Tool Health ci-dessous.

## Job Engine

`POST /api/jobs` accepte soit `profile` (résolu contre les profils de l'outil, fusionné avec `options`), soit `options` seul (arguments bruts). Dans les deux cas, `registry.build_command()` valide le résultat final de façon identique. Voir [api.md](api.md).

## Tool Health

`kali/agent/main.py::_check_tool_health` tente `<exécutable> --version` puis, en repli, `--help`, avec un timeout court (5s) — jamais un scan réel. Les 31 vérifications tournent en parallèle (`asyncio.gather` + `run_in_executor`) via `GET /health/tools` côté agent, agrégées par `GET /api/tools/health` côté backend. Limite connue et assumée : un `--version` qui réussit prouve que le binaire se lance, pas que sa fonction réelle marche sous les privilèges actuels du conteneur (ex. `masscan`/`arp-scan`/`netdiscover` nécessitent `CAP_NET_RAW`, ajouté en Phase 12 — voir [security.md](security.md) — un `--version` réussirait même sans cette capacité).

## Ajouter un nouvel outil

1. Vérifier qu'il est réellement installé dans l'image Kali (`docker exec cyberlab-kali which <outil>`) — jamais supposer.
2. Ajouter le paquet apt dans `kali/Dockerfile`, dans le groupe de catégorie approprié.
3. Ajouter `<nom_logique>: <exécutable>` à `CANDIDATE_TOOLS` dans `kali/agent/main.py`.
4. Créer `backend/app/tools/definitions/<outil>.yaml` : `category`, `risk_level`, `ai_allowed`, `arguments`, au moins un `profile`.
5. Si la sortie est structurée, écrire un parser dans `backend/app/tools/parsers/` et l'enregistrer dans `parsers/__init__.py` (sinon `parser: none`, qui reste un choix valide et documenté).
6. Ajouter un extracteur de findings dans `backend/app/findings/extractor.py` si pertinent.
7. Ajouter des tests dans `backend/tests/tools/`.
8. Tester réellement (`docker compose build cyberlab-kali && docker compose up -d`, puis un vrai job via l'API) avant de considérer l'outil `READY` — jamais se fier uniquement à la validation du schéma.
