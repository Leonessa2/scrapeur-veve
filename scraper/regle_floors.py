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
import os
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
PLAFOND_AVANT_2023 = 100000.0   # CONTRAT v4.3 (Preda, 28/11/2026) : bullrun 2021-2022


def plafond(j: Optional[dt.date]) -> float:
    """Plafond d'un floor du jour : 100 000 $ avant le 01/01/2023, sinon 15 000 $."""
    return PLAFOND_AVANT_2023 if (j is not None and j < dt.date(2023, 1, 1)) else PLAFOND
FACTEUR = 20.0
FENETRE_J = 30
JOURS_SUSPECT = 2   # un floor suspect (x20 / /20) compte s'il tient 2 jours de suite
# CONTRAT v4.1 (Preda, 28/11/2026) : sous 1 $ OU a 15 000 $ ou plus, jamais.


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


def _plus_long(en_vigueur_connu: bool, en_vigueur, du_jour, j: dt.date):
    """Floor TENU LE PLUS LONGTEMPS dans la journee (proposition du 27/11, pas
    encore acceptee) : chaque valeur pese la duree pendant laquelle elle a ete
    le floor (de minuit ou de son arrivee jusqu'au changement suivant ou
    minuit). « Pas d'offre » est une valeur comme une autre : si elle a dure le
    plus, la case est vide. Egalite : la valeur en place a la fin du jour."""
    debut_j = dt.datetime.combine(j, dt.time())
    fin_j = debut_j + dt.timedelta(days=1)
    segs = []                       # (valeur, debut)
    if en_vigueur_connu:
        segs.append((en_vigueur, debut_j))
    segs += [(v, ts) for ts, v in du_jour]
    if not segs:
        return None
    duree: Dict[object, float] = defaultdict(float)
    ordre: Dict[object, int] = {}
    for k, (v, t0) in enumerate(segs):
        t1 = segs[k + 1][1] if k + 1 < len(segs) else fin_j
        cle = v if (v is not None and v > 0) else None
        duree[cle] += max((t1 - t0).total_seconds(), 0.0)
        ordre[cle] = k
    gagnant = max(duree, key=lambda c: (duree[c], ordre[c]))
    return gagnant


def floors_du_jour(points: List[Tuple[dt.datetime, Optional[float]]],
                   sortie: Optional[dt.date], collecte: dt.date,
                   methode: str = "mediane") -> List[Tuple[dt.date, Optional[float]]]:
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
            du_jour.append(points[i])
            i += 1
        if methode == "plus_long":
            out.append((j, _plus_long(connu, en_vigueur, du_jour, j)))
        else:
            releves = ([en_vigueur] if connu else []) + [v for _, v in du_jour]
            valides = [v for v in releves if v is not None and v > 0]
            out.append((j, statistics.median(valides) if valides else None))
        if du_jour:
            connu, en_vigueur = True, du_jour[-1][1]
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
        suspect = f < PLANCHER or f >= plafond(j)       # v4.3 : 15 000 $ pile suspect ; 100 000 $ avant 2023
        if not suspect and fen:
            med = statistics.median(fen)
            if med > 0 and (f > med * FACTEUR or f < med / FACTEUR):
                suspect = True
        if not suspect and f >= PLAFOND and not fen:
            suspect = True          # v4.3 : 15 000 $ ou plus sans historique des 30 jours -> suspect
        marques.append((j, f, suspect))
        hist.append(f)
        hist_j.append(j)
    valides = candidats(marques)
    if not valides:
        return marques, None, None, None, None
    ath = max(valides, key=lambda v: (v[0], -v[1].toordinal()))
    atl = min(valides, key=lambda v: (v[0], v[1].toordinal()))
    return marques, ath[0], ath[1], atl[0], atl[1]


def candidats(marques) -> List[Tuple[float, dt.date]]:
    """Floors du jour valides (v4.1) : (valeur, jour)."""
    valides = []
    debut_serie = 0                 # indice du 1er jour de la serie de meme floor
    for i, (j, f, s) in enumerate(marques):
        if i > 0 and (marques[i - 1][1] != f or (j - marques[i - 1][0]).days != 1):
            debut_serie = i
        if f is None:
            continue
        if f < PLANCHER or f >= plafond(j):
            continue                # sous 1 $, ou 15 000 $ ou plus : jamais (v4.1)
        if not s:
            valides.append((f, j))
            continue
        if f >= PLAFOND:
            continue                # v4.3 : 15 000 $ ou plus (avant 2023) ne compte que s'il n'est pas suspect
        if i - debut_serie + 1 == JOURS_SUSPECT:
            # suspect, mais floor du jour assez de jours de suite : compte, date = 1er jour
            valides.append((f, marques[debut_serie][0]))
    return valides


# ─────────────── CONTRAT v4.2 : garde-fous de l'ATH (Preda, 28/11/2026) ───────────────
VENTES_DEBUT = dt.date(2026, 7, 31)     # nos ventes en dollars commencent la
LIMITE_DEBUT = dt.date(2023, 1, 1)      # avant : aucune limite (sommets 2021-2022)
X_REFERENCE = 3.0                        # apres le 31/07 : <= 3 x reference
X_FLOOR_ACTUEL = 100.0                   # 01/01/2023 -> 30/07/2026 : <= 100 x floor actuel
X_VENTE_FLOOR = 20.0                     # une vente > 20 x le floor du jour n'est pas une reference


def reference_ventes(ventes, jours: Dict[dt.date, Optional[float]]) -> Optional[float]:
    """Plus haute vente reelle fiable (1 $ <= prix < 15 000 $, et pas plus de
    20 x le floor du jour de sa date)."""
    bonnes = []
    for d, p in ventes:
        if p is None or not (PLANCHER <= p < PLAFOND):
            continue
        fj = jours.get(d)
        if fj and p > X_VENTE_FLOOR * fj:
            continue
        bonnes.append(p)
    return max(bonnes) if bonnes else None


def ath_plausible(f: float, j: Optional[dt.date], ref: Optional[float],
                  floor_actuel: Optional[float]) -> bool:
    if j is not None and j < LIMITE_DEBUT:
        return True
    if j is not None and j >= VENTES_DEBUT:
        return not (ref and f > X_REFERENCE * ref)
    return not (floor_actuel and f > X_FLOOR_ACTUEL * floor_actuel)


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


TROU_DEBUT, TROU_FIN = dt.date(2026, 9, 30), dt.date(2026, 11, 25)


def _periode_couverte(d: Optional[dt.date], premier: dt.date, sans_trou: bool,
                      collecte: dt.date) -> str:
    """La date d'un ATH/ATL « venu du tracker » tombe-t-elle dans une periode que
    NOTRE historique couvre ? Sinon, le remplacer donnerait un faux ATH plus bas
    (ou un faux ATL plus haut) : on ne sait pas ce qui s'est passe la."""
    if d is None:
        return "date_inconnue"
    if d < premier:
        return "non_couverte_avant_premiere_donnee"
    if d > collecte:
        return "non_couverte_date_future"
    if not sans_trou and TROU_DEBUT <= d <= TROU_FIN:
        return "non_couverte_trou_comics"   # trou du 30/09 au 25/11 non comble (faux trait droit)
    return "couverte"


def garder_tracker(valeur: Optional[float], periode: str) -> bool:
    """Decision de Preda (27/11) : hors periode couverte (avant notre 1re donnee,
    trou des comics, date future ou absente), on garde la valeur du tracker,
    a condition qu'elle soit entre 1 $ et 15 000 $ ; sinon notre valeur."""
    return (periode != "couverte" and valeur is not None
            and PLANCHER <= valeur < PLAFOND)        # v4.1 : 15 000 $ pile exclu


def _nombre_txt(f: Optional[float]) -> str:
    return "" if f is None else ("%.6f" % f).rstrip("0").rstrip(".")


def lignes_changement(marques):
    """Fichier « floor du jour » : une ligne seulement quand le floor du jour ou
    `floor_suspect` change (un jour sans ligne garde la valeur de la veille).
    Rend [(jour, floor_txt, suspect_txt)] ; floor vide = pas d'offre."""
    out, avant = [], object()
    for j, f, s_ in marques:
        cle = (_nombre_txt(f), "oui" if (s_ and f is not None) else "")
        if cle != avant:
            out.append((j, cle[0], cle[1]))
            avant = cle
    return out


def _une_fiche(p, sortie, collecte, methode):
    jours = floors_du_jour(p, sortie, collecte, methode)
    return appliquer(jours)


def comparer(prix: str, catalogue: str, collecte: dt.date, sortie_csv: str = "",
             methodes=("mediane", "plus_long"), floors_jour: str = "") -> dict:
    pts = lire_points(prix)
    with gzip.open(catalogue, "rt", encoding="utf-8") as f:
        cat = list(csv.DictReader(f))
    cle = "uuid" if cat and "uuid" in cat[0] else "veve_uuid"
    n: Dict[str, int] = defaultdict(int)
    n["fiches_catalogue"] = len(cat)
    dif = lambda a, b: (a is None) != (b is None) or (
        a is not None and b is not None and abs(a - b) > max(0.01, 0.005 * max(a, b)))
    ech = []
    fj = None
    if floors_jour:
        fj = gzip.open(floors_jour, "wt", encoding="utf-8", newline="")
        fj_w = csv.writer(fj, lineterminator="\n")
        fj_w.writerow(["veve_uuid", "date", "floor", "floor_suspect"])
    for r in cat:
        u = (r.get(cle) or "").strip().lower()
        p = pts.get(u)
        if not p:
            continue
        n["fiches_avec_points"] += 1
        sortie = date_libre(r.get("release_date"))
        premier = p[0][0].date()
        avant = any(t.date() < TROU_DEBUT for t, _ in p)
        dedans = any(TROU_DEBUT <= t.date() <= TROU_FIN for t, _ in p)
        # Le trou ne concerne que les comics (prices-full n'ecrit qu'au changement :
        # un collectible sans point dans le trou a juste garde le meme floor).
        comic = (r.get("kind") or "").strip().lower() == "comic"
        sans_trou = dedans or not avant or not comic
        n["fiches_trou_non_comble"] += 0 if sans_trou else 1
        act = {"ath": (nombre(r.get("ath")) or None, date_libre(r.get("ath_date"))),
               "atl": (nombre(r.get("atl")) or None, date_libre(r.get("atl_date")))}
        pts_ok = [f for tt, f in p if f and f > 0 and (not sortie or tt.date() >= sortie)]
        brut_pt = {"ath": max(pts_ok) if pts_ok else None, "atl": min(pts_ok) if pts_ok else None}
        ligne = [u, r.get("name", ""), act["ath"][0], r.get("ath_date"), act["atl"][0], r.get("atl_date")]
        change_une = False
        for m in methodes:
            marques, ath, athd, atl, atld = _une_fiche(p, sortie, collecte, m)
            s_ = sum(1 for _, _, x in marques if x)
            n[f"{m}.jours"] += sum(1 for _, f, _ in marques if f is not None)
            n[f"{m}.jours_suspects"] += s_
            n[f"{m}.fiches_avec_suspect"] += 1 if s_ else 0
            brut = [f for _, f, _ in marques if f is not None]
            med = {"ath": max(brut) if brut else None, "atl": min(brut) if brut else None}
            regle = {"ath": (ath, athd), "atl": (atl, atld)}
            ch = {}
            for k in ("ath", "atl"):
                a, ad = act[k]
                v, vd = regle[k]
                ch[k] = dif(v, a)
                if not ch[k]:
                    if vd and ad and vd != ad:
                        n[f"{m}.{k}_date_seule_change"] += 1
                    continue
                n[f"{m}.{k}_change"] += 1
                if a is None or v is None:
                    classe = "vide"
                else:
                    e = abs(v - a) / max(a, v)
                    classe = "<=5%" if e <= 0.05 else "5-50%" if e <= 0.5 else ">50%"
                n[f"{m}.{k}_ecart_{classe}"] += 1
                if dif(v, med[k]):
                    cause = "filtre_suspects"
                elif not dif(a, brut_pt[k]):
                    cause = "floor_du_jour"
                else:
                    cause = "tracker_" + _periode_couverte(ad, premier, sans_trou, collecte)
                n[f"{m}.{k}_cause_{cause}"] += 1
            if ch["ath"] or ch["atl"]:
                n[f"{m}.ath_ou_atl_change"] += 1
                change_une = True
            ligne += [ath, athd, atl, atld, s_]
            if m == "plus_long" and fj is not None:
                lc = lignes_changement(marques)
                n["floors_jour.lignes"] += len(lc)
                n["floors_jour.fiches"] += 1 if lc else 0
                n["floors_jour.lignes_suspectes"] += sum(1 for x in lc if x[2])
                for j, f_, s_ in lc:
                    fj_w.writerow([u, j.isoformat(), f_, s_])
            if m == "plus_long":
                fin_ch = False
                for k in ("ath", "atl"):
                    a, ad = act[k]
                    per = _periode_couverte(ad, premier, sans_trou, collecte)
                    if garder_tracker(a, per):
                        n[f"final.{k}_tracker_garde"] += 1
                        v, vd = a, ad
                    else:
                        if per != "couverte" and a is not None:
                            n[f"final.{k}_tracker_hors_seuils_remplace"] += 1
                        v, vd = regle[k]
                    if dif(v, a):
                        n[f"final.{k}_change"] += 1; fin_ch = True
                    elif vd and ad and vd != ad:
                        n[f"final.{k}_date_seule_change"] += 1
                if fin_ch:
                    n["final.ath_ou_atl_change"] += 1
        if change_une and len(ech) < 2000:
            ech.append(ligne)
    if fj is not None:
        fj.close()
    if sortie_csv:
        with open(sortie_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            entete = ["veve_uuid", "nom", "ath_actuel", "ath_date_actuelle", "atl_actuel", "atl_date_actuelle"]
            for m in methodes:
                entete += [f"ath_{m}", f"ath_date_{m}", f"atl_{m}", f"atl_date_{m}", f"jours_suspects_{m}"]
            w.writerow(entete)
            w.writerows(ech)
    return dict(n)


if __name__ == "__main__":
    prix, cat = sys.argv[1], sys.argv[2]
    coll = date_libre(sys.argv[3]) if len(sys.argv) > 3 else dt.date.today()
    res = comparer(prix, cat, coll, "exemples_changements.csv",
                   floors_jour=os.environ.get("FLOORS_JOUR", ""))
    for k in sorted(res):
        print(f"[regle] {k} = {res[k]}")
