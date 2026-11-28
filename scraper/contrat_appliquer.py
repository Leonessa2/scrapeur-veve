"""Applique CONTRAT.md (sections 2, 3.3 et 3.7) au catalogue du jour, AVANT sa
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


def decider(p, r, collecte: dt.date):
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
    regle = {"ath": (ath, athd), "atl": (atl, atld)}
    act = {"ath": (R.nombre(r.get("ath")) or None, R.date_libre(r.get("ath_date"))),
           "atl": (R.nombre(r.get("atl")) or None, R.date_libre(r.get("atl_date")))}
    out = {}
    for k in ("ath", "atl"):
        a, ad = act[k]
        per = R._periode_couverte(ad, premier, sans_trou, collecte)
        out[k] = (a, ad) if R.garder_tracker(a, per) else regle[k]
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
        if not p:
            n["fiches_sans_releve"] += 1
            if athatl:
                for b, k in zip(BRUT, ("ath", "atl", "ath_date", "atl_date")):
                    r[b] = r.get(k, "")
            continue
        marques, fin, act = decider(p, r, collecte)
        if floors:
            for j, f_, s_ in R.lignes_changement(marques):
                fj_lignes.append((u, j.isoformat(), f_, s_))
            n["floors_jour.suspects"] += sum(1 for _, f_, s_ in marques if s_ and f_ is not None)
        # controles 3.5
        for _, f_, _s in marques:
            if f_ is not None and f_ <= 0:
                n["controle_floor_a_zero"] += 1
        if athatl:
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
