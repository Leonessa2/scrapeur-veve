"""Applique CONTRAT.md v4.3 (sections 2, 3.3 et 3.7) au catalogue du jour, AVANT sa
publication par catalogue-export.yml. Trois interrupteurs, tous eteints par
defaut (go de Preda du 28/11/2026, publication dans l'ordre de la section 3.8) :

  CONTRAT_OFFRES_VIDES=1   colonne `listings` du catalogue -> vide (section 2)
  CONTRAT_FLOORS_JOUR=1    ecrit floors_jour.csv.gz + floors_jour.json (3.7)
  CONTRAT_ATH_ATL=1        `ath`/`atl`/dates selon la regle (3.3) ; les valeurs
                           du tracker passent dans `ath_brut`, `atl_brut`,
                           `ath_brut_date`, `atl_brut_date` (colonnes ajoutees)

Usage : python -m scraper.contrat_appliquer <catalogue.csv.gz> <prices.csv.gz>
        [dossier_sortie]  -> ecrit <dossier>/catalogue.csv.gz (+ floors_jour.*)
Le floor du jour du catalogue est ajoute comme dernier releve (maintenant).
⛔ Un controle de la section 3.5 qui echoue -> sortie 1, rien n'est ecrit.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import sys
from collections import Counter

from scraper import regle_floors as R

BRUT = ["ath_brut", "atl_brut", "ath_brut_date", "atl_brut_date"]


def _allume(nom: str) -> bool:
    return os.environ.get(nom, "0").strip() == "1"


def charger_ventes() -> dict:
    """CONTRAT v4.2 : ventes reelles en dollars par fiche -> {uuid: [(jour, $)]}.
    VeVe : `data/veve_ventes.csv` (gems ~ $). StackR : `data/stackr_sales.csv`
    (OMI) x cours du jour, deduit de `ventes_stackr.csv` (release
    etat-ventes-stackr, deja converti au cours gate.io). Jamais de cours voisin."""
    fv = os.environ.get("CONTRAT_VENTES_VEVE", "data/veve_ventes.csv")
    fs = os.environ.get("CONTRAT_VENTES_STACKR", "data/stackr_sales.csv")
    fc = os.environ.get("CONTRAT_COURS_OMI", "contrat_src/ventes_stackr.csv")
    for f in (fv, fs, fc):
        if not os.path.exists(f):
            raise SystemExit(f"[contrat] ⛔ fichier de ventes absent : {f} — rien ne doit etre publie.")
    import statistics
    taux = {}
    with open(fc, encoding="utf-8", newline="") as f:
        for x in csv.DictReader(f):
            u, o = R.nombre(x.get("price_usd")), R.nombre(x.get("price_omi"))
            if x.get("marche") == "stackr" and u and o:
                taux.setdefault(x["ts_utc"][:10], []).append(u / o)
    taux = {d: statistics.median(v) for d, v in taux.items()}
    ventes = {}
    with open(fv, encoding="utf-8", newline="") as f:
        for x in csv.DictReader(f):
            p = R.nombre(x.get("price_usd"))
            d = R.date_libre(x.get("ts_utc"))
            if p is not None and d:
                ventes.setdefault(x["element_id"].strip().lower(), []).append((d, p))
    with open(fs, encoding="utf-8", newline="") as f:
        for x in csv.DictReader(f):
            o = R.nombre(x.get("price_omi"))
            j = (x.get("ts_utc") or "")[:10]
            if o is not None and j in taux:
                ventes.setdefault(x["element_id"].strip().lower(), []).append((R.date_libre(j), o * taux[j]))
    return ventes


def decider(p, r, collecte: dt.date, ventes=None, floor_actuel=None):
    """Une fiche -> (marques du jour, {'ath': (v, d), 'atl': (v, d)}) selon la
    regle decidee (floor tenu le plus longtemps + tracker garde hors periode
    couverte, entre 1 $ et 15 000 $). Meme logique que `regle_floors.comparer`
    (bloc « final »), dont les comptes ont servi au go."""
    sortie = R.date_libre(r.get("release_date"))
    jours = R.floors_du_jour(p, sortie, collecte, "plus_long")
    marques, ath, athd, atl, atld = R.appliquer(jours)
    premier = p[0][0].date()
    avant = any(t.date() < R.TROU_DEBUT for t, _ in p)
    dedans = any(R.TROU_DEBUT <= t.date() <= R.TROU_FIN for t, _ in p)
    comic = (r.get("kind") or "").strip().lower() == "comic"
    sans_trou = dedans or not avant or not comic
    # v4.2 : l'ATH ne retient que les floors du jour plausibles
    jd = dict(jours)
    ref_v = R.reference_ventes(ventes or [], jd)
    ref = max([v for v in (ref_v, floor_actuel) if v] or [0]) or None
    cand = [(f, j) for f, j in R.candidats(marques) if R.ath_plausible(f, j, ref, floor_actuel)]
    if cand:
        m = max(cand, key=lambda v: (v[0], -v[1].toordinal()))
        ath, athd = m
    else:
        ath, athd = None, None
    regle = {"ath": (ath, athd), "atl": (atl, atld)}
    act = {"ath": (R.nombre(r.get("ath")) or None, R.date_libre(r.get("ath_date"))),
           "atl": (R.nombre(r.get("atl")) or None, R.date_libre(r.get("atl_date")))}
    out = {}
    for k in ("ath", "atl"):
        a, ad = act[k]
        per = R._periode_couverte(ad, premier, sans_trou, collecte)
        garder = R.garder_tracker(a, per)
        if garder and k == "ath":
            garder = R.ath_plausible(a, ad, ref, floor_actuel)
        out[k] = (a, ad) if garder else regle[k]
    # v4.2 : l'ATL suit l'ATH quand l'ATH passe dessous
    va, vl = out["ath"][0], out["atl"][0]
    if va is not None and vl is not None and vl > va:
        out["atl"] = out["ath"]
    return marques, out, act


def _dif(a, b):
    return (a is None) != (b is None) or (
        a is not None and b is not None and abs(a - b) > max(0.01, 0.005 * max(a, b)))


def appliquer_catalogue(cat_in: str, prix: str, dossier: str, collecte: dt.date,
                        maintenant: dt.datetime, offres: bool, floors: bool, athatl: bool) -> Counter:
    n = Counter()
    with gzip.open(cat_in, "rt", encoding="utf-8", newline="") as f:
        lec = csv.DictReader(f)
        entete = list(lec.fieldnames or [])
        lignes = list(lec)
    cle = "uuid" if "uuid" in entete else "veve_uuid"
    n["fiches"] = len(lignes)
    pts = R.lire_points(prix) if (floors or athatl) else {}
    ventes = charger_ventes() if athatl else None
    if ventes is not None:
        n["ventes.fiches"] = len(ventes)
    fj_lignes = []
    for r in lignes:
        u = (r.get(cle) or "").strip().lower()
        if offres:
            if (r.get("listings") or "").strip() != "":
                n["offres_videes"] += 1
            r["listings"] = ""
        if not (floors or athatl):
            continue
        p = list(pts.get(u, []))
        f_jour = R.nombre(r.get("floor"))
        if not p or p[-1][1] != f_jour:          # le floor du catalogue = releve de maintenant
            if p or f_jour:
                p.append((maintenant, f_jour if f_jour and f_jour > 0 else None))
        sortie = R.date_libre(r.get("release_date"))
        pas_sortie = sortie is not None and sortie > collecte
        if athatl and (pas_sortie or not p):
            # 3.3 : fiche pas encore sortie -> ATH/ATL vides ; sans releve, la
            # valeur du tracker gardee reste soumise aux seuils 1 $ / 15 000 $.
            for b, k in zip(BRUT, ("ath", "atl", "ath_date", "atl_date")):
                r[b] = r.get(k, "")
            ch = False
            for k in ("ath", "atl"):
                a = R.nombre(r.get(k)) or None
                garder = (not pas_sortie) and R.garder_tracker(a, "sans_releve")
                if not garder:
                    if a is not None:
                        ch = True
                        n[f"{k}_change"] += 1
                    r[k] = ""; r[k + "_date"] = ""
                else:
                    d = R.date_libre(r.get(k + "_date"))
                    if d and d > collecte:
                        n[f"{k}_date_future_videe"] += 1
                        r[k + "_date"] = ""
            if ch:
                n["ath_ou_atl_change"] += 1
            n["fiches_pas_sorties" if pas_sortie else "fiches_sans_releve"] += 1
            if not p or not floors:
                continue           # une fiche pas sortie garde son floor du jour (3.7), rien de plus
        if not p:
            n["fiches_sans_releve"] += 1
            continue
        marques, fin, act = decider(p, r, collecte, ventes.get(u, []) if ventes is not None else None,
                                    f_jour if f_jour and f_jour > 0 else None)
        if floors:
            for j, f_, s_ in R.lignes_changement(marques):
                fj_lignes.append((u, j.isoformat(), f_, s_))
            n["floors_jour.suspects"] += sum(1 for _, f_, s_ in marques if s_ and f_ is not None)
        # controles 3.5
        for _, f_, _s in marques:
            if f_ is not None and f_ <= 0:
                n["controle_floor_a_zero"] += 1
        if athatl and not pas_sortie:
            for b, k in zip(BRUT, ("ath", "atl", "ath_date", "atl_date")):
                r[b] = r.get(k, "")
            ch = False
            for k in ("ath", "atl"):
                v, d = fin[k]
                if _dif(v, act[k][0]):
                    n[f"{k}_change"] += 1; ch = True
                if d and d > collecte:
                    n[f"{k}_date_future_videe"] += 1       # 3.3 : jamais apres la collecte
                    d = None
                r[k] = R._nombre_txt(v)
                r[k + "_date"] = d.isoformat() if d else ""
            if ch:
                n["ath_ou_atl_change"] += 1
            va, vl = fin["ath"][0], fin["atl"][0]
            if va is not None and vl is not None and vl > va:
                n["controle_atl_au_dessus_ath"] += 1
    if athatl:
        entete += [b for b in BRUT if b not in entete]
        for r in lignes:                      # 3.5 (v4.1) : ATH/ATL entre 1 $ et moins de 15 000 $
            for k in ("ath", "atl"):
                v = R.nombre(r.get(k))
                if v is not None and not (R.PLANCHER <= v < R.plafond(R.date_libre(r.get(k + "_date")))):
                    n["controle_hors_seuils"] += 1
            va, fl = R.nombre(r.get("ath")), R.nombre(r.get("floor"))
            d_a = R.date_libre(r.get("ath_date"))
            if va is not None and fl and va >= 10000 and va >= 100 * fl \
                    and not (d_a and d_a < R.LIMITE_DEBUT):
                n["controle_ath_10000_100x"] += 1       # v4.2 : test de Preda, bloquant (hors ATH d'avant 2023)
            vl = R.nombre(r.get("atl"))
            if va is not None and vl is not None and vl > va:
                n["controle_atl_au_dessus_ath_final"] += 1
    if floors or athatl:
        # v4.1 : floor actuel a 15 000 $ ou plus -> vide dans `catalogue` (apres le
        # calcul du floor du jour, qui garde le releve reel et le marque suspect).
        for r in lignes:
            v = R.nombre(r.get("floor"))
            if v is not None and v >= R.PLAFOND:
                r["floor"] = ""
                n["floor_vide_15000_ou_plus"] += 1
        for r in lignes:
            v = R.nombre(r.get("floor"))
            if v is not None and v >= R.PLAFOND:
                n["controle_floor_15000_ou_plus"] += 1
    os.makedirs(dossier, exist_ok=True)
    with gzip.open(os.path.join(dossier, "catalogue.csv.gz"), "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=entete, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(lignes)
    if floors:
        fj_lignes.sort(key=lambda x: (x[0], x[1]))
        chemin = os.path.join(dossier, "floors_jour.csv.gz")
        with gzip.open(chemin, "wt", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["veve_uuid", "date", "floor", "floor_suspect"])
            w.writerows(fj_lignes)
        h = hashlib.sha256(open(chemin, "rb").read()).hexdigest()
        with open(os.path.join(dossier, "floors_jour.json"), "w", encoding="utf-8") as f:
            json.dump({"collecte": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "lignes": len(fj_lignes), "sha256": h}, f, indent=1)
        n["floors_jour.lignes"] = len(fj_lignes)
        n["floors_jour.fiches"] = len({x[0] for x in fj_lignes})
    return n


def main() -> int:
    cat_in, prix = sys.argv[1], sys.argv[2]
    dossier = sys.argv[3] if len(sys.argv) > 3 else "contrat"
    offres, floors, athatl = (_allume("CONTRAT_OFFRES_VIDES"), _allume("CONTRAT_FLOORS_JOUR"),
                              _allume("CONTRAT_ATH_ATL"))
    print(f"[contrat] interrupteurs : offres_vides={int(offres)} floors_jour={int(floors)} ath_atl={int(athatl)}")
    if not (offres or floors or athatl):
        print("[contrat] tout est eteint : rien a faire.")
        return 0
    maintenant = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    n = appliquer_catalogue(cat_in, prix, dossier, maintenant.date(), maintenant, offres, floors, athatl)
    for k in sorted(n):
        print(f"[contrat] {k} = {n[k]}")
    with open(os.path.join(dossier, "compte.json"), "w", encoding="utf-8") as f:
        json.dump(dict(n), f, indent=1, sort_keys=True)
    ko = {k: v for k, v in n.items() if k.startswith("controle_") and v}
    if ko:
        print(f"[contrat] ⛔ controle(s) en echec : {ko} — rien ne doit etre publie.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
