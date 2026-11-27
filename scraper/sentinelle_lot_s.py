# ⚠️ DEPOT : Leonessa2/scrapeur-veve   ·   CHEMIN : scraper/sentinelle_lot_s.py
"""🛰️ Lot S (27/11/2026) — ce que la sentinelle ne voyait pas.

POURQUOI CE MODULE EXISTE
-------------------------
Du 09/10 au 27/11/2026, toute la chaine du grand livre est restee figee :
l'ancien `PREDA_TOKEN` a expire le 09/10, « Fusion transferts » est tombee
chaque mardi, `analytics.yml` a refuse sa source chaque mercredi, le ledger
writer a refuse d'ecrire chaque jeudi. Six semaines. Personne ne l'a vu, parce
que :

  1. la sentinelle postait avec `urllib` -> Cloudflare (devant Discord) renvoie
     403 « error code: 1010 » au client Python par defaut, l'erreur etait
     avalee, le run restait VERT : AUCUN battement quotidien n'arrivait ;
  2. le filet de jetonveve ne connaissait pas `analytics-derived` ni `burns`,
     et n'a jamais ete declenche par « Fusion transferts » (mesure du 27/11 :
     aucune execution du filet apres ses 7 echecs) ;
  3. personne ne regardait la DATE des releases, seulement la couleur des runs ;
  4. personne ne connaissait la date d'expiration des jetons.

CE QUE CE MODULE AJOUTE (six controles, tous lus par l'API GitHub)
-----------------------------------------------------------------
  A. FRAICHEUR  — l'age du FICHIER publie, pas du run (release + asset).
  B. ECHECS     — tout run en echec ou depasse sur les dernieres heures, dans
                  chaque depot, qu'il soit dans le filet ou non.
  C. ETATS      — un workflow desactive par GitHub (60 jours sans activite)
                  ou a la main.
  D. CADENCE    — floor-watch : moins de N passages reussis en 24 h, ou aucun
                  depuis H heures.
  E. JETONS     — chaque jeton present : accepte ou refuse, et sa date
                  d'expiration lue dans la reponse de GitHub ; les jetons
                  declares (ranges ailleurs) : date notee a la main.
  F. DATES      — dates ATH/ATL dans le futur pour une fiche deja sortie.

⛔ Comme dans `sentinelle_absence` : TOUT le raisonnement est pur, le reseau
vit dans `SourceLotS`, que les tests remplacent par un double.
⛔ Un controle qui n'a pas pu lire le DIT (ligne ⚫), il ne se tait jamais.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

API = "https://api.github.com"
UA = "sentinelle-lot-s (https://github.com/Leonessa2/scrapeur-veve)"


# ─────────────────────────────────────────────────────────────────────────────
# OUTILS PURS
# ─────────────────────────────────────────────────────────────────────────────
def date_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def date_libre(s: str | None) -> date | None:
    """⭐ Le catalogue melange deux formats : `release_date` en JJ/MM/AAAA
    (Sheet en reglage francais), `ath_date` / `atl_date` en AAAA-MM-JJ.
    Comparer les textes tels quels donne n'importe quoi (mesure du 27/11)."""
    s = (s or "").strip()[:10]
    for f in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def jours(td: timedelta) -> float:
    return td.total_seconds() / 86400


def fr_date(d: datetime | date) -> str:
    return d.strftime("%d/%m/%Y")


# ─────────────────────────────────────────────────────────────────────────────
# LA SEULE PARTIE QUI TOUCHE LE RESEAU
# ─────────────────────────────────────────────────────────────────────────────
def _http(url: str, jeton: str = "", brut: bool = False):
    """Rend (code, entetes, donnees, erreur). ⭐ Une erreur n'est jamais un vide."""
    h = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if jeton:
        h["Authorization"] = f"Bearer {jeton}"
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            corps = r.read()
            return r.status, dict(r.headers), (corps if brut else json.loads(corps)), ""
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), None, f"HTTP {e.code}"
    except Exception as e:                                   # reseau, DNS, delai
        return 0, {}, None, type(e).__name__


class SourceLotS:
    def __init__(self, jeton: str):
        self.jeton = jeton

    def assets(self, owner, depot, tag):
        _, _, d, err = _http(f"{API}/repos/{owner}/{depot}/releases/tags/{tag}", self.jeton)
        if err:
            return None, err
        return [{"name": a["name"], "updated_at": date_iso(a.get("updated_at"))}
                for a in (d.get("assets") or [])], ""

    def workflows(self, owner, depot):
        _, _, d, err = _http(f"{API}/repos/{owner}/{depot}/actions/workflows?per_page=100",
                             self.jeton)
        if err:
            return None, err
        return [{"nom": w["name"], "fichier": w["path"].rsplit("/", 1)[-1],
                 "etat": w["state"]} for w in d.get("workflows") or []], ""

    def runs_depuis(self, owner, depot, depuis: datetime, fichier: str | None = None):
        base = (f"{API}/repos/{owner}/{depot}/actions/"
                + (f"workflows/{fichier}/runs" if fichier else "runs"))
        crit = depuis.strftime("%Y-%m-%dT%H:%M:%SZ")
        out = []
        for page in range(1, 6):                  # 500 runs au plus : large
            _, _, d, err = _http(f"{base}?per_page=100&page={page}&created=%3E%3D{crit}",
                                 self.jeton)
            if err:
                return None, err
            lot = d.get("workflow_runs") or []
            out += [{"nom": r["name"], "fichier": r["path"].rsplit("/", 1)[-1],
                     "conclusion": r.get("conclusion"), "statut": r.get("status"),
                     "evenement": r.get("event"), "cree": date_iso(r["created_at"]),
                     "fini": date_iso(r.get("updated_at")), "lien": r.get("html_url")}
                    for r in lot]
            if len(lot) < 100:
                break
        return out, ""

    def jeton_info(self, jeton: str):
        """⭐ GitHub renvoie la date d'expiration d'un jeton personnel dans
        l'entete `github-authentication-token-expiration` de CHAQUE reponse.
        Absente = jeton sans expiration (ou jeton d'app)."""
        code, h, _, err = _http(f"{API}/repos/Leonessa2/scrapeur-veve", jeton)
        exp = {k.lower(): v for k, v in h.items()}.get("github-authentication-token-expiration")
        return code, exp, err

    def telecharger(self, url: str):
        _, _, d, err = _http(url, "", brut=True)
        return d, err


# ─────────────────────────────────────────────────────────────────────────────
# A. FRAICHEUR DES FICHIERS PUBLIES
# ─────────────────────────────────────────────────────────────────────────────
def controle_fraicheur(entrees: list, src, maintenant: datetime) -> list:
    """Chaque entree : release, depot (owner/depot), asset (nom ou "*" = le plus
    recent), max_age_j, critique, sens (ce que ca casse).
    ⭐⭐ On regarde la date DU FICHIER, pas celle du run : un run vert qui ne
    depose rien laisse le fichier vieillir, et c'est ca qu'on veut voir."""
    L = []
    for e in entrees:
        owner, depot = e["depot"].split("/", 1)
        lst, err = src.assets(owner, depot, e["release"])
        nom = f"`{e['release']}`"
        if err:
            L.append(("aveugle", f"⚫ {nom} ({depot}) — **je n'ai pas pu lire la release** "
                                 f"({err}). ⛔ Ce n'est pas « elle est a jour »."))
            continue
        if e.get("asset", "*") == "*":
            dates = [a["updated_at"] for a in lst if a["updated_at"]]
            quoi = "fichier le plus recent"
        else:
            dates = [a["updated_at"] for a in lst if a["name"] == e["asset"] and a["updated_at"]]
            quoi = f"`{e['asset']}`"
        if not dates:
            L.append(("alarme", f"🔥 {nom} ({depot}) — {quoi} **introuvable** dans la release."))
            continue
        d = max(dates)
        age = jours(maintenant - d)
        if age > float(e["max_age_j"]):
            tete = "🔥" if e.get("critique") else "🟠"
            L.append(("alarme", f"{tete} {nom} ({depot}) — {quoi} date du **{fr_date(d)}** : "
                                f"**{age:.0f} jours** (maximum {e['max_age_j']}). "
                                f"{e.get('sens', '')}".rstrip()))
        else:
            L.append(("ok", f"{nom} {age:.1f} j"))
    return L


# ─────────────────────────────────────────────────────────────────────────────
# B. ECHECS RECENTS — tous les workflows, filet ou pas
# ─────────────────────────────────────────────────────────────────────────────
def controle_echecs(depots: list, src, maintenant: datetime, fenetre_h: float,
                    attendus: list | None = None) -> list:
    """⭐⭐⭐ Ne depend d'AUCUNE liste de noms : le filet de jetonveve n'a jamais
    ete declenche par « Fusion transferts » (7 echecs, 0 alerte) et ne
    connaissait pas `analytics-derived`. Ici, on demande a GitHub « qu'est-ce
    qui a echoue ? », point.
    `attendus` : [{depot, fichier, jusqu_au (AAAA-MM-JJ), raison}] — un echec
    annonce a l'avance s'affiche comme tel, sans alarme."""
    attendus = attendus or []
    depuis = maintenant - timedelta(hours=fenetre_h)
    L = []
    for od in depots:
        owner, depot = od.split("/", 1)
        runs, err = src.runs_depuis(owner, depot, depuis)
        if err:
            L.append(("aveugle", f"⚫ Echecs de `{depot}` : **rien pu lire** ({err})."))
            continue
        par, dernier_net = {}, {}
        for r in runs:
            if r["conclusion"] in ("failure", "timed_out", "startup_failure"):
                par.setdefault(r["fichier"], []).append(r)
            # ⭐ « dernier resultat net » : un run annule ou saute ne dit rien.
            if r["conclusion"] in ("success", "failure", "timed_out", "startup_failure"):
                if r["fichier"] not in dernier_net or r["cree"] > dernier_net[r["fichier"]]["cree"]:
                    dernier_net[r["fichier"]] = r
        for fichier, lot in sorted(par.items()):
            # ⭐⭐ Echec PUIS succes = repare (cas des 4 taches le 26/11) : on le
            #   dit en une ligne, sans sonner. Sinon le canal crie sur du passe
            #   et apprend a etre ignore.
            if dernier_net.get(fichier, {}).get("conclusion") == "success":
                L.append(("info", f"`{depot}/{fichier}` : {len(lot)} echec(s) puis un succes"))
                continue
            att = next((a for a in attendus if a["depot"] == od and a["fichier"] == fichier
                        and (date_libre(a.get("jusqu_au")) or date.min) >= maintenant.date()),
                       None)
            dernier = max(lot, key=lambda r: r["cree"])
            txt = (f"`{depot}/{fichier}` — **{len(lot)} echec(s)** en {fenetre_h:.0f} h "
                   f"(dernier : {dernier['cree']:%d/%m %H:%M} UTC) {dernier['lien']}")
            if att:
                L.append(("attendu", f"⚪ {txt} — attendu : {att.get('raison', '')}"))
            else:
                L.append(("alarme", f"🔴 {txt}"))
    return L


# ─────────────────────────────────────────────────────────────────────────────
# C. WORKFLOWS DESACTIVES
# ─────────────────────────────────────────────────────────────────────────────
def controle_etats(depots: list, src) -> list:
    """GitHub desactive tout seul un workflow planifie apres 60 jours sans
    activite dans un depot public (`disabled_inactivity`) : il ne tourne plus,
    n'echoue plus, et AUCUN run rouge ne le dira jamais."""
    L = []
    for od in depots:
        owner, depot = od.split("/", 1)
        lst, err = src.workflows(owner, depot)
        if err:
            L.append(("aveugle", f"⚫ Etats de `{depot}` : **rien pu lire** ({err})."))
            continue
        for w in lst:
            if w["etat"] == "disabled_inactivity":
                L.append(("alarme", f"🔥 `{depot}/{w['fichier']}` **desactive par GitHub** "
                                    f"(60 jours sans activite) : il ne tourne plus du tout."))
            elif w["etat"] == "disabled_manually":
                L.append(("info", f"`{depot}/{w['fichier']}` desactive a la main"))
    return L


# ─────────────────────────────────────────────────────────────────────────────
# D. CADENCE (floor-watch)
# ─────────────────────────────────────────────────────────────────────────────
def controle_cadence(entrees: list, src, maintenant: datetime) -> list:
    """Chaque entree : depot (owner/depot), fichier, min_24h, silence_max_h, sens.
    ⭐ Sans le pinger cron-job.org, GitHub ne lance qu'environ 3,6 passages par
    jour au lieu de ~50 (mesure du 26/11) — sans aucun run rouge."""
    L = []
    for e in entrees:
        owner, depot = e["depot"].split("/", 1)
        runs, err = src.runs_depuis(owner, depot, maintenant - timedelta(hours=24), e["fichier"])
        if err:
            L.append(("aveugle", f"⚫ Cadence de `{e['fichier']}` : **rien pu lire** ({err})."))
            continue
        ok = sorted((r["fini"] or r["cree"]) for r in runs if r["conclusion"] == "success")
        pinger = sum(1 for r in runs if r["evenement"] == "repository_dispatch")
        silence = jours(maintenant - ok[-1]) * 24 if ok else None
        pb = []
        if len(ok) < int(e["min_24h"]):
            pb.append(f"**{len(ok)} passages reussis en 24 h** (minimum {e['min_24h']}, "
                      f"dont {pinger} lances par le pinger)")
        if silence is None or silence > float(e["silence_max_h"]):
            pb.append("**aucun passage reussi en 24 h**" if silence is None
                      else f"**aucun passage reussi depuis {silence:.1f} h** "
                           f"(maximum {e['silence_max_h']} h)")
        if pb:
            L.append(("alarme", f"🔥 `{depot}/{e['fichier']}` — " + " ; ".join(pb) + ". "
                                + e.get("sens", "")))
        else:
            L.append(("ok", f"{e['fichier']} {len(ok)} passages/24 h"))
    return L


# ─────────────────────────────────────────────────────────────────────────────
# E. JETONS
# ─────────────────────────────────────────────────────────────────────────────
def _exp(s: str | None) -> datetime | None:
    """Formats vus : « 2026-12-01 00:00:00 UTC », « 2026-12-01 00:00:00 +0100 »."""
    if not s:
        return None
    s = s.strip()
    for f in ("%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, f)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def controle_jetons(presents: dict, declares: list, src, maintenant: datetime,
                    preavis_j: int = 14) -> list:
    """`presents` : {NOM: valeur} — jetons passes en secret a ce workflow.
    `declares` : [{nom, expire_le (AAAA-MM-JJ ou vide), range, sert_a}] — jetons
    rangés AILLEURS (cron-job.org, PC de Preda), dont GitHub ne peut rien dire.
    ⭐⭐⭐ Lecon du 09/10/2026 : un jeton expire ne fait pas de bruit, il fait
    echouer LES AUTRES, une semaine plus tard, ailleurs."""
    L = []
    for nom, val in sorted(presents.items()):
        if not val:
            L.append(("alarme", f"🔥 Jeton `{nom}` : **secret absent ou vide** sur ce depot."))
            continue
        code, exp, err = src.jeton_info(val)
        if code in (401, 403):
            L.append(("alarme", f"🔥 Jeton `{nom}` **refuse par GitHub** (HTTP {code}) : "
                                f"expire ou revoque. Tout ce qui l'utilise va echouer."))
            continue
        if err and code == 0:
            L.append(("aveugle", f"⚫ Jeton `{nom}` : rien pu verifier ({err})."))
            continue
        d = _exp(exp)
        if exp and not d:
            L.append(("aveugle", f"⚫ Jeton `{nom}` : date d'expiration illisible (« {exp} »)."))
        elif d is None:
            L.append(("ok", f"{nom} valide, sans expiration"))
        else:
            reste = jours(d - maintenant)
            if reste <= preavis_j:
                L.append(("alarme", f"⏰ Jeton `{nom}` **expire le {fr_date(d)}** "
                                    f"(dans {max(reste, 0):.0f} jours) : a renouveler AVANT."))
            else:
                L.append(("ok", f"{nom} valide jusqu'au {fr_date(d)}"))
    for j in declares:
        d = _exp(j.get("expire_le") or "")
        if d is None:
            L.append(("info", f"jeton `{j['nom']}` ({j.get('range', '?')}) : date d'expiration "
                              f"**non notee** dans le manifeste"))
            continue
        reste = jours(d - maintenant)
        if reste <= preavis_j:
            L.append(("alarme", f"⏰ Jeton `{j['nom']}` ({j.get('range', '?')}) **expire le "
                                f"{fr_date(d)}** (dans {max(reste, 0):.0f} jours) — sert a : "
                                f"{j.get('sert_a', '?')}. A renouveler AVANT."))
        else:
            L.append(("ok", f"{j['nom']} jusqu'au {fr_date(d)} (declare)"))
    return L


# ─────────────────────────────────────────────────────────────────────────────
# F. DATES DANS LE FUTUR (catalogue publie)
# ─────────────────────────────────────────────────────────────────────────────
def dates_futures(lignes, aujourd_hui: date) -> list:
    """Fiches DEJA SORTIES dont l'ATH ou l'ATL est date apres aujourd'hui.
    ⭐ Les fiches pas encore sorties sont exclues : le tracker les date du jour
    de sortie, c'est attendu (mesure du 26/11)."""
    out = []
    for x in lignes:
        sortie = date_libre(x.get("release_date"))
        if sortie is None or sortie > aujourd_hui:
            continue
        futs = [k for k in ("ath_date", "atl_date")
                if (date_libre(x.get(k)) or date.min) > aujourd_hui]
        if futs:
            out.append((x.get("name", "?"), futs))
    return out


def controle_dates(entree: dict | None, src, aujourd_hui: date) -> list:
    if not entree:
        return []
    data, err = src.telecharger(entree["url"])
    if err:
        return [("aveugle", f"⚫ Dates futures : catalogue illisible ({err}).")]
    try:
        txt = gzip.decompress(data).decode("utf-8") if entree["url"].endswith(".gz") \
            else data.decode("utf-8")
        lignes = list(csv.DictReader(io.StringIO(txt)))
    except Exception as e:
        return [("aveugle", f"⚫ Dates futures : catalogue illisible ({type(e).__name__}).")]
    if not lignes:
        return [("alarme", "🔥 Dates futures : le catalogue publie est **vide**.")]
    fut = dates_futures(lignes, aujourd_hui)
    if not fut:
        return [("ok", "dates futures 0")]
    noms = sorted({n for n, _ in fut})
    return [("alarme", f"🟠 **{len(fut)} fiche(s) deja sortie(s) avec une date ATH/ATL dans "
                       f"le futur** au catalogue : " + ", ".join(noms[:4])
             + ("…" if len(noms) > 4 else ""))]


# ─────────────────────────────────────────────────────────────────────────────
# LE RAPPORT
# ─────────────────────────────────────────────────────────────────────────────
TITRES = [("fraicheur", "📦 Fraicheur des fichiers publies"),
          ("echecs", "🔴 Echecs recents"),
          ("etats", "⏸️ Workflows desactives"),
          ("cadence", "⏱️ Cadence"),
          ("jetons", "🔑 Jetons"),
          ("dates", "📅 Dates")]


def rapport_lot_s(resultats: dict) -> tuple[str, bool]:
    """`resultats` : {controle: [(genre, texte)]}. Rend (texte, alarme).
    ⭐ Les « ok » ne s'affichent qu'en une ligne de compte : le canal doit
    montrer ce qui ne va pas, pas noyer."""
    L, alarme = [], False
    oks, infos = 0, []
    for cle, titre in TITRES:
        lot = resultats.get(cle) or []
        visibles = [t for g, t in lot if g in ("alarme", "aveugle", "attendu")]
        oks += sum(1 for g, _ in lot if g == "ok")
        infos += [t for g, t in lot if g == "info"]
        if any(g in ("alarme", "aveugle") for g, _ in lot):
            alarme = True
        if visibles:
            L.append(f"**{titre}**")
            L += visibles
    if infos:
        L.append("_A savoir : " + " · ".join(infos) + "._")
    L.append(f"_Lot S : {oks} controle(s) sans probleme._")
    return "\n".join(L), alarme


def executer(cfg: dict, src, presents: dict, maintenant: datetime | None = None,
             rapide: bool = False) -> tuple[str, bool]:
    """`cfg` = la section `lot_s` du manifeste. En mode `rapide` (toutes les
    3 h) : seulement ce qui peut casser en quelques heures (cadence, jetons
    refuses, fraicheur marquee `rapide: true`)."""
    m = maintenant or datetime.now(timezone.utc)
    depots = cfg.get("depots") or []
    fr = [e for e in cfg.get("fraicheur") or [] if not rapide or e.get("rapide")]
    res = {"fraicheur": controle_fraicheur(fr, src, m),
           "cadence": controle_cadence(cfg.get("cadence") or [], src, m),
           "jetons": controle_jetons(presents, [] if rapide else cfg.get("jetons_declares") or [],
                                     src, m, int(cfg.get("preavis_jetons_j", 14)))}
    if not rapide:
        res["echecs"] = controle_echecs(depots, src, m, float(cfg.get("echecs_fenetre_h", 26)),
                                        cfg.get("echecs_attendus"))
        res["etats"] = controle_etats(depots, src)
        res["dates"] = controle_dates(cfg.get("dates_futures"), src, m.date())
    return rapport_lot_s(res)
