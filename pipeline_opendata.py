#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline open data — Cockpit Maison Bastide (version CI / GitHub Actions)
=========================================================================
Version autonome du notebook Pipeline_OpenData_Bastide.ipynb :
- lit les référentiels dans referentiels/*.csv (sinon jeu de démonstration) ;
- collecte : Etalab, BCE (Frankfurter), BODACC, Google News RSS, ADEME
  Base Carbone, Eurostat, Banque mondiale (coton), jours fériés ;
- bonus : si la variable d'environnement PAPPERS_TOKEN est définie,
  enrichit aussi via Pappers (comptes annuels, forme juridique) ;
- écrit docs/cockpit_data_v2.json (servable via GitHub Pages).

Conception défensive : chaque section gère ses échecs (⚠ dans le rapport),
le JSON est produit avec ce qui a réussi. Code de sortie 0 sauf si aucune
écriture n'est possible.
"""
import os, re, sys, json, time
from datetime import date, datetime, timedelta

import requests
import pandas as pd
import feedparser

# ── Configuration ────────────────────────────────────────────────────────────
SORTIE        = os.environ.get("SORTIE_JSON", "docs/cockpit_data_v2.json")
PAUSE         = 0.4
JOURS_VEILLE  = 14
MAX_ARTICLES  = 80
PAPPERS_TOKEN = os.environ.get("PAPPERS_TOKEN")  # optionnel

THEMES_VEILLE = {
    "Prêt-à-porter & retail":   'prêt-à-porter enseigne OR boutique France',
    "Textile & sourcing":       'textile sourcing OR "near-shoring" OR coton prix',
    "E-commerce mode":          'e-commerce mode habillement France',
    "Conjoncture consommation": 'consommation habillement France INSEE',
}
RSS_PERSO = []  # flux RSS sectoriels additionnels

DEMO_CLIENTS = [
    {"code": "CW001", "nom_recherche": "Galeries Lafayette", "canal": "Wholesale",
     "ca_interne": 1418, "encours": 486, "dso": 88},
    {"code": "CW002", "nom_recherche": "Printemps", "canal": "Wholesale",
     "ca_interne": 640, "encours": 150, "dso": 61},
]
DEMO_FOURNISSEURS = [
    {"code": "F013", "nom_recherche": "Filatures Aquitaine", "pays": "France",
     "devise": "EUR", "vol25": 312},
    {"code": "F001", "nom_recherche": "Ningbo Textile", "pays": "Chine",
     "devise": "USD", "vol25": 3630},
]

session = requests.Session()
session.headers.update({"User-Agent": "CockpitBastide/2.1 (refresh hebdomadaire CI)"})
RAPPORT = {}

def api_get(url, params=None, tries=3, as_json=True):
    for i in range(tries):
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 * (i + 1)); continue
            r.raise_for_status()
            return r.json() if as_json else r.text
        except Exception as e:
            if i == tries - 1:
                print(f"   ⚠ {url.split('?')[0]} : {e}")
                return None
            time.sleep(1.5 * (i + 1))

def section(nom):
    """Décorateur : isole une section, consigne succès/échec dans RAPPORT."""
    def deco(fn):
        def run(*a, **k):
            try:
                out = fn(*a, **k)
                return out
            except Exception as e:
                print(f"   ⚠ section {nom} : {e}")
                RAPPORT[nom] = f"échec : {e}"
                return None
        return run
    return deco

# ── 1 · Référentiels + Etalab (+ Pappers si token) ──────────────────────────
def charger(nom, demo):
    chemin = os.path.join("referentiels", nom)
    if os.path.exists(chemin):
        print(f"→ {chemin}")
        return pd.read_csv(chemin)
    print(f"→ démo intégrée ({nom} absent)")
    return pd.DataFrame(demo)

def etalab(query):
    d = api_get("https://recherche-entreprises.api.gouv.fr/search",
                {"q": str(query), "per_page": 1}) or {}
    r = (d.get("results") or [{}])[0]; siege = r.get("siege") or {}
    return {"siren": r.get("siren"),
            "nom_officiel": r.get("nom_complet") or r.get("nom_raison_sociale"),
            "naf": r.get("activite_principale"),
            "effectif_tranche": r.get("tranche_effectif_salarie"),
            "statut": {"A": "Active", "C": "Cessée"}.get(r.get("etat_administratif")),
            "ville_officielle": siege.get("libelle_commune")}

def pappers(siren):
    if not (PAPPERS_TOKEN and siren):
        return {}
    d = api_get("https://api.pappers.fr/v2/entreprise",
                {"api_token": PAPPERS_TOKEN, "siren": siren}) or {}
    fin = (d.get("finances") or [{}])[0]
    return {"forme_juridique": d.get("forme_juridique"),
            "annee_comptes": fin.get("annee"),
            "ca_publie": fin.get("chiffre_affaires"),
            "resultat_publie": fin.get("resultat"),
            "capitaux_propres": fin.get("capitaux_propres"),
            "procedure_collective": bool(d.get("procedures_collectives"))}

@section("identite_tiers")
def enrichir_tiers():
    clients      = charger("clients_bastide.csv", DEMO_CLIENTS).to_dict("records")
    fournisseurs = charger("fournisseurs_bastide.csv", DEMO_FOURNISSEURS).to_dict("records")
    resolus = 0
    for t in clients + fournisseurs:
        q = t.get("siren") or t.get("nom_recherche") or t.get("nom")
        eta = etalab(q) if q else {}
        t.update(eta)
        if eta.get("siren"):
            resolus += 1
            t.update(pappers(eta["siren"]))
        time.sleep(PAUSE)
    RAPPORT["identite_tiers"] = f"{resolus}/{len(clients)+len(fournisseurs)} résolus" + \
                                (" (+Pappers)" if PAPPERS_TOKEN else "")
    return clients, fournisseurs

# ── 2 · Change BCE ───────────────────────────────────────────────────────────
@section("change_bce")
def fx_bce(devises=("USD", "CNY", "GBP")):
    latest = api_get("https://api.frankfurter.app/latest",
                     {"from": "EUR", "to": ",".join(devises)}) or {}
    debut = (date.today() - timedelta(days=365)).isoformat()
    hist  = api_get(f"https://api.frankfurter.app/{debut}..",
                    {"from": "EUR", "to": ",".join(devises)}) or {}
    rates, serie, var = latest.get("rates", {}), hist.get("rates", {}), {}
    if serie:
        d0 = sorted(serie)[0]
        for dv in devises:
            a, b = serie[d0].get(dv), rates.get(dv)
            if a and b: var[dv] = round((b / a - 1) * 100, 1)
    if rates:
        RAPPORT["change_bce"] = f"{len(rates)} devises au {latest.get('date')}"
    return {"date": latest.get("date"), "base": "EUR", "rates": rates,
            "variation_1an_pct": var}

# ── 3 · BODACC ───────────────────────────────────────────────────────────────
ALERTE_RX = re.compile(r"collective|sauvegarde|redressement|liquidation|radiation", re.I)

@section("bodacc")
def veille_bodacc(tiers):
    out = []
    for t in tiers:
        ann = []
        if t.get("siren"):
            d = api_get("https://bodacc-datadila.opendatasoft.com/api/records/1.0/search/",
                        {"dataset": "annonces-commerciales", "q": t["siren"],
                         "rows": 5, "sort": "dateparution"}) or {}
            for rec in d.get("records", []):
                f = rec.get("fields", {})
                ann.append({"date": f.get("dateparution"), "type": f.get("familleavis_lib"),
                            "tribunal": f.get("tribunal"),
                            "detail": (f.get("publicationavis") or "")[:80]})
            time.sleep(PAUSE)
        alerte = any(ALERTE_RX.search(str(a.get("type") or "")) for a in ann)
        t["bodacc_alerte"] = alerte
        out.append({"code": t.get("code"),
                    "nom": t.get("nom_officiel") or t.get("nom_recherche"),
                    "siren": t.get("siren"), "annonces": ann, "alerte": alerte})
    RAPPORT["bodacc"] = f"{sum(1 for v in out if v['alerte'])} alerte(s) / {len(out)} tiers"
    return out

# ── 4 · Veille presse ────────────────────────────────────────────────────────
@section("veille_presse")
def collecter_veille():
    limite = datetime.now() - timedelta(days=JOURS_VEILLE)
    vus, articles = set(), []
    sources = [(th, feedparser.parse(
        "https://news.google.com/rss/search?q=" + requests.utils.quote(q) +
        "&hl=fr&gl=FR&ceid=FR:fr")) for th, q in THEMES_VEILLE.items()]
    sources += [("Flux perso", feedparser.parse(u)) for u in RSS_PERSO]
    for theme, feed in sources:
        for e in feed.entries[:25]:
            titre = (e.get("title") or "").strip()
            cle = titre.lower()[:90]
            if not titre or cle in vus: continue
            try: pub = datetime(*e.published_parsed[:6])
            except Exception: pub = datetime.now()
            if pub < limite: continue
            vus.add(cle)
            articles.append({"theme": theme, "titre": titre,
                             "source": (e.get("source") or {}).get("title") or feed.feed.get("title", ""),
                             "date": pub.date().isoformat(), "lien": e.get("link")})
        time.sleep(0.3)
    articles = sorted(articles, key=lambda a: a["date"], reverse=True)[:MAX_ARTICLES]
    RAPPORT["veille_presse"] = f"{len(articles)} articles"
    return articles

def prompt_digest(articles):
    lignes = "\n".join(f"- [{a['theme']}] {a['date']} — {a['titre']} ({a['source']})"
                       for a in articles[:40])
    return ("Tu es le contrôleur de gestion de Maison Bastide (prêt-à-porter, 11 boutiques, "
            "wholesale, e-commerce, sourcing international). Voici la veille des "
            f"{JOURS_VEILLE} derniers jours :\n{lignes}\n\n"
            "Produis un digest en 4 rubriques (Concurrence & retail · Matières & sourcing · "
            "Réglementation · Conjoncture) : pour chaque rubrique, 2-3 faits saillants et leur "
            "implication concrète pour Bastide. Termine par les 3 signaux à surveiller. "
            "N'invente rien qui ne soit pas dans la liste.")

# ── 5 · CO₂ ADEME ────────────────────────────────────────────────────────────
@section("co2_ademe")
def co2_ademe():
    def facteurs(recherche, n=5):
        for slug in ("base-carboner", "base-carbone"):
            d = api_get(f"https://data.ademe.fr/data-fair/api/v1/datasets/{slug}/lines",
                        {"q": recherche, "size": n,
                         "select": "Nom_base_français,Total_poste_non_décomposé,Unité_français"})
            if d and d.get("results"):
                return [{"nom": r.get("Nom_base_français"),
                         "valeur": r.get("Total_poste_non_décomposé"),
                         "unite": r.get("Unité_français")} for r in d["results"]]
        return []
    def choisir(cands, defaut):
        for r in cands:
            v = r.get("valeur")
            if isinstance(v, (int, float)) and 0 < v < 3000:
                return {"valeur": v, "source": r["nom"], "unite": r.get("unite")}
        return {"valeur": defaut, "source": "défaut cockpit (ADEME indisponible)",
                "unite": "gCO2e/t.km"}
    mar = choisir(facteurs("porte-conteneurs transport marchandises"), 12)
    rou = choisir(facteurs("articulé PTAC transport marchandises routier"), 90)
    RAPPORT["co2_ademe"] = f"maritime={mar['valeur']} / routier={rou['valeur']}"
    return {"provenance": "ADEME Base Carbone®",
            "maritime_g_tkm": mar, "routier_g_tkm": rou}

# ── 6 · Conjoncture ──────────────────────────────────────────────────────────
@section("conjoncture")
def conjoncture():
    out = {}
    d = api_get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr",
                {"format": "JSON", "lang": "FR", "geo": "FR", "coicop": "CP03",
                 "unit": "RCH_A", "lastTimePeriod": "12"})
    if d and "value" in d:
        inv = {v: k for k, v in d["dimension"]["time"]["category"]["index"].items()}
        out["ipch_habillement_fr_pct"] = dict(sorted(
            {inv[int(i)]: v for i, v in d["value"].items()}.items()))
    try:
        url = ("https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/"
               "related/CMO-Historical-Data-Monthly.xlsx")
        raw = session.get(url, timeout=60); raw.raise_for_status()
        xl = pd.read_excel(raw.content, sheet_name="Monthly Prices", header=4)
        col = [c for c in xl.columns if "Cotton" in str(c)]
        if col:
            s = xl[["Unnamed: 0", col[0]]].dropna().tail(13)
            out["coton_usd_kg"] = {str(r.iloc[0]): round(float(r.iloc[1]), 3)
                                   for _, r in s.iterrows()}
    except Exception as e:
        print("   ⚠ Pink Sheet Banque mondiale :", e)
    jf = api_get(f"https://calendrier.api.gouv.fr/jours-feries/metropole/{date.today().year}.json") or {}
    out["jours_feries"] = jf
    RAPPORT["conjoncture"] = (f"IPCH {len(out.get('ipch_habillement_fr_pct', {}))} mois · "
                              f"coton {len(out.get('coton_usd_kg', {}))} mois · "
                              f"{len(jf)} fériés")
    return out

# ── Assemblage ───────────────────────────────────────────────────────────────
def main():
    print("=== Rafraîchissement cockpit Bastide —", datetime.now().isoformat(timespec="seconds"), "===")
    tiers = enrichir_tiers() or ([], [])
    clients, fournisseurs = tiers if isinstance(tiers, tuple) else ([], [])
    fx      = fx_bce() or {}
    bod     = veille_bodacc(clients + fournisseurs) or []
    presse  = collecter_veille() or []
    co2     = co2_ademe() or {}
    conj    = conjoncture() or {}

    paquet = {
        "meta": {"genere_le": datetime.now().isoformat(timespec="seconds"),
                 "pipeline": "refresh-hebdo CI v2.1",
                 "sources": ["Etalab", "BCE/Frankfurter", "BODACC", "Google News RSS",
                             "ADEME Base Carbone", "Eurostat", "Banque mondiale",
                             "calendrier.api.gouv.fr"] + (["Pappers"] if PAPPERS_TOKEN else []),
                 "rapport_sections": RAPPORT},
        "fx": fx, "clients": clients, "fournisseurs": fournisseurs,
        "veille": {"bodacc": bod, "presse": presse,
                   "prompt_digest": prompt_digest(presse)},
        "co2": co2, "conjoncture": conj,
    }
    os.makedirs(os.path.dirname(SORTIE) or ".", exist_ok=True)
    with open(SORTIE, "w", encoding="utf-8") as f:
        json.dump(paquet, f, ensure_ascii=False, indent=1)
    print(f"✅ écrit : {SORTIE}")
    print(json.dumps(RAPPORT, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("✗ échec fatal :", e)
        sys.exit(1)
