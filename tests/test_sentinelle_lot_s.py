# ⚠️ DEPOT : Leonessa2/scrapeur-veve   ·   CHEMIN : tests/test_sentinelle_lot_s.py
"""Lot S (27/11/2026). Chaque test reproduit une panne REELLE du 09/10 au 27/11.
⛔ ZERO RESEAU : la source est un double."""

import urllib.error
from datetime import date, datetime, timedelta, timezone

from scraper import sentinelle_absence as S
from scraper import sentinelle_lot_s as L

M = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def h(x):
    return M - timedelta(hours=x)


class Faux:
    def __init__(self, assets=None, runs=None, wf=None, jetons=None, fichier=None, err=None):
        self._assets, self._runs, self._wf = assets or {}, runs or {}, wf or {}
        self._jetons, self._fichier, self._err = jetons or {}, fichier, err or {}

    def assets(self, o, d, tag):
        if tag in self._err:
            return None, self._err[tag]
        return self._assets.get(tag, []), ""

    def runs_depuis(self, o, d, depuis, fichier=None):
        if d in self._err:
            return None, self._err[d]
        lst = self._runs.get((d, fichier), [])
        return [r for r in lst if r["cree"] >= depuis], ""

    def workflows(self, o, d):
        return self._wf.get(d, []), ""

    def jeton_info(self, val):
        return self._jetons[val]

    def telecharger(self, url):
        return self._fichier, ""


def run(fichier, concl, quand, ev="schedule"):
    return {"nom": fichier, "fichier": fichier, "conclusion": concl, "statut": "completed",
            "evenement": ev, "cree": quand, "fini": quand, "lien": "https://x"}


# A ───────────────────────────────────────────────────────────────────────────
def test_fraicheur_voit_analytics_derived_du_14_10():
    src = Faux(assets={"analytics-derived": [
        {"name": "ledger_full.csv.gz", "updated_at": datetime(2026, 10, 14, 11, 3, tzinfo=timezone.utc)},
        {"name": "meta.csv", "updated_at": M}]})          # ⭐ un autre fichier frais ne masque rien
    r = L.controle_fraicheur([{"release": "analytics-derived", "depot": "Leonessa2/jetonveve",
                               "asset": "ledger_full.csv.gz", "max_age_j": 7, "critique": True}], src, M)
    assert r[0][0] == "alarme" and "14/10/2026" in r[0][1] and "44 jours" in r[0][1]


def test_fraicheur_ne_crie_pas_sur_un_fichier_frais():
    src = Faux(assets={"catalogue": [{"name": "catalogue.csv.gz", "updated_at": h(20)}]})
    r = L.controle_fraicheur([{"release": "catalogue", "depot": "Leonessa2/jetonveve",
                               "asset": "catalogue.csv.gz", "max_age_j": 2}], src, M)
    assert r[0][0] == "ok"


def test_fraicheur_asset_etoile_prend_le_plus_recent():
    src = Faux(assets={"chain-archive-daily": [
        {"name": "transfers_daily_2026-11-18.csv.gz", "updated_at": datetime(2026, 11, 19, 10, tzinfo=timezone.utc)},
        {"name": "transfers_daily_2026-11-17.csv.gz", "updated_at": datetime(2026, 11, 18, 10, tzinfo=timezone.utc)}]})
    r = L.controle_fraicheur([{"release": "chain-archive-daily", "depot": "Leonessa2/scrapeur-veve",
                               "asset": "*", "max_age_j": 2}], src, M)
    assert r[0][0] == "alarme" and "19/11/2026" in r[0][1]


def test_fraicheur_illisible_n_est_pas_a_jour():
    src = Faux(err={"ledger-data": "HTTP 401"})
    r = L.controle_fraicheur([{"release": "ledger-data", "depot": "Leonessa2/scrapeur-veve",
                               "asset": "x", "max_age_j": 8}], src, M)
    assert r[0][0] == "aveugle"


def test_fraicheur_fichier_absent_crie():
    src = Faux(assets={"ledger-data": [{"name": "autre.csv", "updated_at": M}]})
    r = L.controle_fraicheur([{"release": "ledger-data", "depot": "Leonessa2/scrapeur-veve",
                               "asset": "wallet_profiles.csv.gz", "max_age_j": 8}], src, M)
    assert r[0][0] == "alarme" and "introuvable" in r[0][1]


# B ───────────────────────────────────────────────────────────────────────────
def test_echecs_vus_sans_aucune_liste_de_noms():
    """burns.yml n'etait dans AUCUN filet : il echouait chaque jour depuis le 07/10."""
    src = Faux(runs={("jetonveve", None): [run("burns.yml", "failure", h(2)),
                                            run("burns.yml", "failure", h(9)),
                                            run("floor-watch.yml", "success", h(1)),
                                            run("floor-watch.yml", "cancelled", h(3))]})
    r = L.controle_echecs(["Leonessa2/jetonveve"], src, M, 26)
    assert len(r) == 1 and r[0][0] == "alarme" and "burns.yml" in r[0][1] and "2 echec" in r[0][1]


def test_echec_attendu_ne_sonne_pas_mais_se_voit():
    src = Faux(runs={("jetonveve", None): [run("analytics.yml", "failure", h(5))]})
    att = [{"depot": "Leonessa2/jetonveve", "fichier": "analytics.yml",
            "jusqu_au": "2026-12-31", "raison": "source trop vieille"}]
    r = L.controle_echecs(["Leonessa2/jetonveve"], src, M, 26, att)
    assert r[0][0] == "attendu"


def test_echec_attendu_perime_resonne():
    src = Faux(runs={("jetonveve", None): [run("analytics.yml", "failure", h(5))]})
    att = [{"depot": "Leonessa2/jetonveve", "fichier": "analytics.yml", "jusqu_au": "2026-11-01"}]
    assert L.controle_echecs(["Leonessa2/jetonveve"], src, M, 26, att)[0][0] == "alarme"


def test_echec_suivi_d_un_succes_ne_sonne_pas():
    """26/11 : daily.yml rouge le matin, reparee l'apres-midi."""
    src = Faux(runs={("scrapeur-veve", None): [run("daily.yml", "failure", h(20)),
                                                run("daily.yml", "success", h(2)),
                                                run("burns.yml", "success", h(20)),
                                                run("burns.yml", "failure", h(2)),
                                                run("burns.yml", "cancelled", h(1))]})
    r = dict((t.split("`")[1], g) for g, t in L.controle_echecs(["Leonessa2/scrapeur-veve"], src, M, 26))
    assert r == {"scrapeur-veve/daily.yml": "info", "scrapeur-veve/burns.yml": "alarme"}


def test_echecs_hors_fenetre_ignores():
    src = Faux(runs={("jetonveve", None): [run("burns.yml", "failure", h(40))]})
    assert L.controle_echecs(["Leonessa2/jetonveve"], src, M, 26) == []


# C ───────────────────────────────────────────────────────────────────────────
def test_desactive_par_github_crie_desactive_a_la_main_informe():
    src = Faux(wf={"jetonveve": [
        {"nom": "a", "fichier": "a.yml", "etat": "disabled_inactivity"},
        {"nom": "b", "fichier": "merge-transfers.yml", "etat": "disabled_manually"},
        {"nom": "c", "fichier": "c.yml", "etat": "active"}]})
    r = L.controle_etats(["Leonessa2/jetonveve"], src)
    assert [g for g, _ in r] == ["alarme", "info"]


# D ───────────────────────────────────────────────────────────────────────────
CAD = [{"depot": "Leonessa2/jetonveve", "fichier": "floor-watch.yml", "min_24h": 12, "silence_max_h": 6}]


def test_cadence_sans_pinger_crie():
    """Du 20/10 au 26/11 : ~3,6 passages par jour, tous verts."""
    src = Faux(runs={("jetonveve", "floor-watch.yml"): [run("floor-watch.yml", "success", h(x)) for x in (1, 8, 15, 22)]})
    r = L.controle_cadence(CAD, src, M)
    assert r[0][0] == "alarme" and "4 passages" in r[0][1]


def test_cadence_silence_de_7_h_crie_meme_avec_assez_de_passages():
    src = Faux(runs={("jetonveve", "floor-watch.yml"): [run("floor-watch.yml", "success", h(7 + x / 2)) for x in range(30)]})
    r = L.controle_cadence(CAD, src, M)
    assert r[0][0] == "alarme" and "depuis 7.0 h" in r[0][1]


def test_cadence_normale_ne_crie_pas():
    src = Faux(runs={("jetonveve", "floor-watch.yml"): [run("floor-watch.yml", "success", h(x / 2), "repository_dispatch") for x in range(1, 47)]})
    assert L.controle_cadence(CAD, src, M)[0][0] == "ok"


# E ───────────────────────────────────────────────────────────────────────────
def test_jeton_refuse_crie():
    """L'ancien PREDA_TOKEN, a partir du 09/10."""
    src = Faux(jetons={"v": (401, None, "HTTP 401")})
    r = L.controle_jetons({"PREDA_TOKEN": "v"}, [], src, M)
    assert r[0][0] == "alarme" and "refuse" in r[0][1]


def test_jeton_qui_expire_bientot_crie_avant():
    src = Faux(jetons={"v": (200, "2026-12-05 00:00:00 UTC", "")})
    r = L.controle_jetons({"JETONVEVE_TOKEN": "v"}, [], src, M)
    assert r[0][0] == "alarme" and "05/12/2026" in r[0][1]


def test_jeton_lointain_ou_sans_expiration_ne_crie_pas():
    src = Faux(jetons={"a": (200, "2027-11-26 00:00:00 +0100", ""), "b": (200, None, "")})
    r = L.controle_jetons({"A": "a", "B": "b"}, [], src, M)
    assert [g for g, _ in r] == ["ok", "ok"]


def test_secret_vide_crie():
    r = L.controle_jetons({"PREDA_TOKEN": ""}, [], Faux(), M)
    assert r[0][0] == "alarme"


def test_jeton_declare_proche_crie_date_absente_informe():
    d = [{"nom": "PINGER_FLOORWATCH", "expire_le": "2026-12-01", "range": "cron-job.org"},
         {"nom": "DEV_SCRAPEUR", "expire_le": ""}]
    r = L.controle_jetons({}, d, Faux(), M)
    assert [g for g, _ in r] == ["alarme", "info"]


# F ───────────────────────────────────────────────────────────────────────────
def test_dates_futures_exclut_les_fiches_pas_encore_sorties():
    """Mesure du 27/11 : 30 fiches a date future, dont 7 deja sorties (Happy New Year 2026)."""
    lignes = [
        {"name": "Happy New Year! 2026 - Tier 1", "release_date": "31/12/2025 16:00:00",
         "ath_date": "", "atl_date": "2026-12-31"},
        {"name": "Moon Knight #1 (1980)", "release_date": "01/12/2026",
         "ath_date": "2026-12-01", "atl_date": "2026-12-01"},
        {"name": "Normal", "release_date": "01/01/2024", "ath_date": "2024-05-01",
         "atl_date": "2026-11-27"}]
    r = L.dates_futures(lignes, date(2026, 11, 27))
    assert r == [("Happy New Year! 2026 - Tier 1", ["atl_date"])]


def test_catalogue_vide_crie():
    import gzip
    src = Faux(fichier=gzip.compress(b"name,release_date,ath_date,atl_date\n"))
    r = L.controle_dates({"url": "https://x/catalogue.csv.gz"}, src, date(2026, 11, 27))
    assert r[0][0] == "alarme"


# RAPPORT ─────────────────────────────────────────────────────────────────────
def test_rapport_sans_probleme_tient_en_une_ligne():
    txt, al = L.rapport_lot_s({"fraicheur": [("ok", "x")], "jetons": [("ok", "y")]})
    assert not al and txt == "_Lot S : 2 controle(s) sans probleme._"


def test_rapport_aveugle_est_une_alarme():
    txt, al = L.rapport_lot_s({"echecs": [("aveugle", "⚫ rien pu lire")]})
    assert al and "rien pu lire" in txt


def test_attendu_seul_n_est_pas_une_alarme():
    txt, al = L.rapport_lot_s({"echecs": [("attendu", "⚪ analytics attendu")]})
    assert not al and "attendu" in txt


# POSTER (la vraie panne du battement) ────────────────────────────────────────
def test_poster_envoie_un_user_agent_qui_n_est_pas_python(monkeypatch):
    vus = []

    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def faux_urlopen(req, timeout=0):
        vus.append(req)
        return R()
    monkeypatch.setattr(S.urllib.request, "urlopen", faux_urlopen)
    assert S.poster("bonjour", "https://discord.example/api/webhooks/1/x") is True
    ua = vus[0].get_header("User-agent")
    assert ua and "Python-urllib" not in ua
    assert vus[0].full_url.endswith("?wait=true")


def test_poster_refuse_rend_false(monkeypatch):
    """26/11 : 403 de Cloudflare, erreur avalee, run vert. Plus jamais."""
    import io

    def faux_urlopen(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b"error code: 1010"))
    monkeypatch.setattr(S.urllib.request, "urlopen", faux_urlopen)
    assert S.poster("x", "https://discord.example/api/webhooks/1/x") is False


def test_poster_sans_webhook_rend_false():
    assert S.poster("x", "") is False


def test_les_blocs_coupent_aux_lignes_et_restent_sous_2000():
    msg = "\n".join("ligne %d " % i + "x" * 80 for i in range(100))
    b = S._blocs(msg)
    assert all(len(x) <= 1900 for x in b) and "\n".join(b) == msg


def test_le_manifeste_reel_porte_le_lot_s():
    import yaml
    d = yaml.safe_load(open("data/manifeste_sentinelles.yml", encoding="utf-8"))["lot_s"]
    rel = {e["release"] for e in d["fraicheur"]}
    assert {"analytics-derived", "transfers-full", "ledger-data", "chain-archive-daily"} <= rel
    ad = next(e for e in d["fraicheur"] if e["release"] == "analytics-derived")
    assert ad["max_age_j"] == 7
