# ⚠️ DEPOT : Leonessa2/scrapeur-veve   ·   CHEMIN : scraper/regle_floors.py
"""📐 La regle des floors, ATH et ATL (decidee par Preda le 27/11/2026).

Texte de reference : CONTRAT-brouillon.md, section 3 (RESEAU.md « Regle des
floors, ATH et ATL »). Ce module la CALCULE ; il ne publie rien. Il sert
d'abord a COMPTER ce qui changerait (go de Preda avant toute publication).

D'OU VIENNENT LES « RELEVES DU JOUR »
------------------------------------
`prices-full` (jetonveve) est ecrit APPEND-ON-CHANGE : une ligne seulement
quand le floor (ou le nombre d'offres) change. Un floor reste identique toute la
journee n'y laisse aucune ligne — il a pourtant ete releve. Decision (Scrapeur,
27/11) :
  * releves du jour J = le floor EN VIGUEUR a 00:00 UTC (dernier point avant J)
    + chaque changement de la journee ;
  * un jour sans changement garde le floor de la veille (meme releve) ;
  * floor du jour = la MEDIANE de ces releves (un seul releve = ce releve).

LA REGLE (CONTRAT 3.1 a 3.3)
----------------------------
  * pas d'offre (floor vide ou <= 0) = case vide ; aucun floor avant la date de
    sortie, aucun apres la date de collecte ;
  * suspect : < 1 $, > 15 000 $, ou > x20 / < :20 de la mediane des floors du
    jour des 30 jours precedents (sans jour precedent : seulement 1 $ / 15 000 $,
    precision validee par Preda le 27/11) ;
  * ATH / ATL = plus haut / plus bas des floors du jour valides ; un floor
    suspect ne compte que s'il est le floor du jour DEUX jours de suite, et
    jamais sous 1 $.
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import gzip
import io
import statistics
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

PLANCHER = 1.0
PLAFOND = 15000.0
FACTEUR = 20.0
FENETRE_J = 30


def nombre(x) -> Optional[float]:
    """Accepte le point ET la virgule (le catalogue est en reglage francais)."""
    s = str(x if x is not None else "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def date_libre(s) -> Optional[dt.date]:
    s = str(s or "").strip()[:10]
    for f in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def floors_du_jour(points: List[Tuple[dt.datetime, Optional[float]]],
                   sortie: Optional[dt.date], collecte: dt.date) -> List[Tuple[dt.date, Optional[float]]]:
    """points : (horodatage UTC, floor) TRIES. Rend [(jour, floor du jour ou None)]
    du premier jour autorise (1er point, ou la sortie si plus tard) jusqu'a la
    date de collecte incluse."""
    if not points:
        return []
    debut = points[0][0].date()
    if sortie and sortie > debut:
        debut = sortie
    i, n = 0, len(points)
    connu, en_vigueur = False, None
    while i < n and points[i][0].date() < debut:       # avant la sortie : seulement l'etat
        connu, en_vigueur = True, points[i][1]
        i += 1
    out = []
    j = debut
    while j <= collecte:
        du_jour = []
        while i < n and points[i][0].date() == j:
            du_jour.append(points[i][1])
            i += 1
        releves = ([en_vigueur] if connu else []) + du_jour
        valides = [v for v in releves if v is not None and v > 0]
        out.append((j, statistics.median(valides) if valides else None))
        if du_jour:
            connu, en_vigueur = True, du_jour[-1]
        j += dt.timedelta(days=1)
    return out


def appliquer(jours: List[Tuple[dt.date, Optional[float]]]):
    """Rend (jours_marques, ath, ath_date, atl, atl_date) ;
    jours_marques = [(jour, floor, suspect)]."""
    marques = []
    hist: List[float] = []
    hist_j: List[dt.date] = []
    for j, f in jours:
        if f is None:
            marques.append((j, None, False))
            continue
        k = bisect.bisect_left(hist_j, j - dt.timedelta(days=FENETRE_J))
        fen = hist[k:]
        suspect = f < PLANCHER or f > PLAFOND
        if not suspect and fen:
            med = statistics.median(fen)
            if med > 0 and (f > med * FACTEUR or f < med / FACTEUR):
                suspect = True
        marques.append((j, f, suspect))
        hist.append(f)
        hist_j.append(j)
    valides = []
    for i, (j, f, s) in enumerate(marques):
        if f is None:
            continue
        if not s:
            valides.append((f, j))
        elif f >= PLANCHER and i > 0 and marques[i - 1][1] == f:
            # suspect, mais floor du jour DEUX jours de suite : compte, date = 1er jour
            valides.append((f, marques[i - 1][0]))
    if not valides:
        return marques, None, None, None, None
    ath = max(valides, key=lambda v: (v[0], -v[1].toordinal()))
    atl = min(valides, key=lambda v: (v[0], v[1].toordinal()))
    return marques, ath[0], ath[1], atl[0], atl[1]


# ─────────────────────────────── la sonde ───────────────────────────────────
def lire_points(chemin: str) -> Dict[str, List[Tuple[dt.datetime, Optional[float]]]]:
    pts: Dict[str, list] = defaultdict(list)
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts = r.get("ts_utc") or ""
            try:
                t = dt.datetime.fromisoformat(ts.replace("Z", "").replace("T", " ")[:19])
            except ValueError:
                continue
            pts[(r.get("veve_uuid") or "").strip().lower()].append((t, nombre(r.get("floor"))))
    for k in pts:
        pts[k].sort(key=lambda p: p[0])
    return pts


def comparer(prix: str, catalogue: str, collecte: dt.date, sortie_csv: str = "") -> dict:
    pts = lire_points(prix)
    with gzip.open(catalogue, "rt", encoding="utf-8") as f:
        cat = list(csv.DictReader(f))
    cle = "uuid" if cat and "uuid" in cat[0] else "veve_uuid"
    n = {"fiches_catalogue": len(cat), "fiches_avec_points": 0, "jours": 0,
         "jours_suspects": 0, "fiches_avec_suspect": 0, "jours_avant_sortie_retires": 0,
         "ath_change": 0, "atl_change": 0, "ath_ou_atl_change": 0,
         "ath_date_change": 0, "atl_date_change": 0, "ath_vide": 0, "atl_vide": 0,
         "ath_cat_vide": 0, "atl_cat_vide": 0}
    ech = []
    for r in cat:
        u = (r.get(cle) or "").strip().lower()
        p = pts.get(u)
        sortie = date_libre(r.get("release_date"))
        a_ath, a_atl = nombre(r.get("ath")), nombre(r.get("atl"))
        if not a_ath:
            n["ath_cat_vide"] += 1
        if not a_atl:
            n["atl_cat_vide"] += 1
        if not p:
            continue
        n["fiches_avec_points"] += 1
        if sortie:
            n["jours_avant_sortie_retires"] += len({t.date() for t, _ in p if t.date() < sortie})
        jours = floors_du_jour(p, sortie, collecte)
        marques, ath, athd, atl, atld = appliquer(jours)
        n["jours"] += sum(1 for _, f, _ in marques if f is not None)
        s = sum(1 for _, _, x in marques if x)
        n["jours_suspects"] += s
        n["fiches_avec_suspect"] += 1 if s else 0
        n["ath_vide"] += 0 if ath else 1
        n["atl_vide"] += 0 if atl else 1
        dif = lambda a, b: (a is None) != (b is None) or (a is not None and b is not None and abs(a - b) > max(0.01, 0.005 * max(a, b)))
        ca, cl = dif(ath, a_ath or None), dif(atl, a_atl or None)
        n["ath_change"] += ca
        n["atl_change"] += cl
        n["ath_ou_atl_change"] += 1 if (ca or cl) else 0
        if not ca and athd and date_libre(r.get("ath_date")) and athd != date_libre(r.get("ath_date")):
            n["ath_date_change"] += 1
        if not cl and atld and date_libre(r.get("atl_date")) and atld != date_libre(r.get("atl_date")):
            n["atl_date_change"] += 1
        if (ca or cl) and len(ech) < 400:
            ech.append([u, r.get("name", ""), a_ath, r.get("ath_date"), ath, athd, a_atl,
                        r.get("atl_date"), atl, atld, s])
    if sortie_csv:
        with open(sortie_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["veve_uuid", "nom", "ath_actuel", "ath_date_actuelle", "ath_regle",
                        "ath_date_regle", "atl_actuel", "atl_date_actuelle", "atl_regle",
                        "atl_date_regle", "jours_suspects"])
            w.writerows(ech)
    return n


if __name__ == "__main__":
    prix, cat = sys.argv[1], sys.argv[2]
    coll = date_libre(sys.argv[3]) if len(sys.argv) > 3 else dt.date.today()
    res = comparer(prix, cat, coll, "exemples_changements.csv")
    for k, v in res.items():
        print(f"[regle] {k} = {v}")
