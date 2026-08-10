# Labs

Le Lab Manager démarre des environnements Docker volontairement vulnérables pour l'apprentissage, isolés du reste du système.

## Architecture

```
Nuxt --(REST via cyberlab-api)--> cyberlab-labmanager --(docker.sock)--> conteneurs de labs
```

Voir [security.md](security.md#lab-manager--le-seul-service-avec-accès-à-dockersock) pour le raisonnement derrière le choix d'isoler `docker.sock` dans un service dédié plutôt que de l'exposer sur l'API principale.

## Catalogue (`labmanager/definitions/*.yaml`)

Un lab est décrit par une définition minimale :

```yaml
name: dvwa
display_name: "Damn Vulnerable Web Application"
description: "..."
image: "vulnerables/web-dvwa:latest"
internal_port: 80
```

Pour l'instant : **DVWA** uniquement (spec : « commencer avec un lab Docker simple »). Ajouter un lab = un nouveau fichier YAML dans `labmanager/definitions/`, aucun code à changer.

## Cycle de vie

| Action | Effet |
|---|---|
| `POST /api/labs?definition=dvwa` | Crée un réseau Docker dédié (`cyberlab-lab-<id>`), lance le conteneur, le connecte aussi à `cyberlab-kali-net`, publie son port interne sur `127.0.0.1:<port aléatoire>`. |
| `POST /api/labs/{id}/start` | Redémarre un conteneur arrêté. |
| `POST /api/labs/{id}/stop` | Arrête le conteneur (état conservé). |
| `POST /api/labs/{id}/reset` | Supprime et recrée le conteneur depuis l'image d'origine — repart d'un état propre (perd les données accumulées, ex. la base DVWA). |
| `DELETE /api/labs/{id}` | Supprime le conteneur et son réseau dédié. |
| `GET /api/labs` | Liste les labs actifs — l'état vient directement de Docker (labels `cyberlab.lab.*`), jamais dupliqué en base. |

## Découverte des cibles

Le conteneur d'un lab est toujours joignable par le conteneur Kali via son nom (`cyberlab-lab-<definition>-<id>`) sur le réseau `cyberlab-kali-net` — utilisable directement comme cible pour un job (`nmap`, `whatweb`, `nikto`) ou dans le terminal intégré, sans configuration supplémentaire.

## Limitation connue

`create_lab`/`reset_lab` peuvent déclencher un premier pull d'image (potentiellement plusieurs minutes). Le Lab Manager déporte ces appels dans un thread pour rester réactif pendant ce temps (voir security.md), et l'API augmente son timeout HTTP à 10 minutes pour ces requêtes en conséquence.
