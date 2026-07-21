# Kit de rafraîchissement hebdomadaire — Cockpit Maison Bastide

Chaque lundi matin, GitHub exécute la collecte open data et committe
`docs/cockpit_data_v2.json`. Zéro serveur à gérer, gratuit (dépôt public
ou minutes incluses d'un dépôt privé).

## Installation (10 minutes, une seule fois)

1. **Créer un dépôt GitHub** (public ou privé), par ex. `cockpit-bastide-data`.
2. **Y déposer le contenu de ce kit** (glisser-déposer via l'interface web
   suffit) : `pipeline_opendata.py`, `requirements.txt`, `referentiels/`,
   `.github/workflows/refresh-hebdo.yml`.
3. **Autoriser le bot à écrire** : *Settings → Actions → General →
   Workflow permissions →* cocher **Read and write permissions** → Save.
4. **Tester tout de suite** : onglet *Actions* → « Rafraîchissement
   hebdomadaire du cockpit » → **Run workflow**. Au vert, le fichier
   `docs/cockpit_data_v2.json` apparaît dans le dépôt.
5. C'est en place : le cron (`lundi 05h17 UTC`) prend le relais chaque semaine.

## Brancher tes vraies données

Remplace les deux CSV du dossier `referentiels/` par tes tiers réels
(mêmes colonnes ; ajoute une colonne `siren` pour fiabiliser la résolution).

## Option Pappers (comptes annuels des tiers)

*Settings → Secrets and variables → Actions → New repository secret* :
nom `PAPPERS_TOKEN`, valeur = ta clé. Le script la détecte tout seul au
run suivant — aucun autre changement.

## Alimenter le cockpit automatiquement (recommandé)

Active **GitHub Pages** : *Settings → Pages → Source : Deploy from a
branch → Branch : main, dossier `/docs`*. Deux usages :

- **JSON seul** : il devient accessible à l'URL
  `https://<toncompte>.github.io/<dépôt>/cockpit_data_v2.json` —
  télécharge-le et importe-le dans l'onglet *Veille & alertes*.
- **Cockpit hébergé (le plus fluide)** : copie aussi les fichiers du
  cockpit (HTML + extensions `epm-stage*`) dans `docs/`. Le cockpit servi
  par Pages trouve `cockpit_data_v2.json` à côté de lui et **se charge
  automatiquement à chaque ouverture** — plus aucun import manuel.
  ⚠ Sur un dépôt public, Pages est public : n'y mets le cockpit que si
  les données de démonstration te conviennent, ou passe le dépôt en privé
  avec Pages privé (offre payante) / garde l'import manuel.

## Personnaliser

- Fréquence : ligne `cron:` du workflow (`"17 5 * * 1,4"` = lundi + jeudi).
- Thèmes de veille / flux RSS : en tête de `pipeline_opendata.py`
  (`THEMES_VEILLE`, `RSS_PERSO`).
- Le run affiche un **rapport par section** dans les logs Actions ; une
  API indisponible met un ⚠ sans bloquer les autres.
