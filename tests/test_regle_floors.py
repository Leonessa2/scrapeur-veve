# ⚠️ DEPOT : Leonessa2/scrapeur-veve   ·   CHEMIN : tests/test_regle_floors.py
"""Regle des floors / ATH / ATL (CONTRAT-brouillon section 3)."""
import datetime as dt

from scraper import regle_floors as R

D = dt.date


def t(j, h=12):
    return dt.datetime(2026, 11, j, h)


def test_mediane_des_releves_annonce_eclair_ignoree():
    """Floor 50 a minuit, une annonce a 5 $ achetee dans la minute, retour a 50."""
    p = [(t(1, 0), 50.0), (t(2, 10), 5.0), (t(2, 10, ), 50.0)]
    j = dict(R.floors_du_jour(p, None, D(2026, 11, 2)))
    assert j[D(2026, 11, 2)] == 50.0


def test_jour_sans_changement_garde_le_floor():
    p = [(t(1), 40.0)]
    assert R.floors_du_jour(p, None, D(2026, 11, 3)) == [(D(2026, 11, 1), 40.0), (D(2026, 11, 2), 40.0), (D(2026, 11, 3), 40.0)]


def test_pas_d_offre_case_vide_et_rien_avant_la_sortie():
    p = [(t(1), 9.99), (t(3), 0.0)]
    j = R.floors_du_jour(p, D(2026, 11, 2), D(2026, 11, 3))
    assert j[0] == (D(2026, 11, 2), 9.99) and j[1] == (D(2026, 11, 3), 9.99)   # mediane(9.99 a minuit, 0 -> vide)
    p = [(t(1), 9.99), (t(2, 0), 0.0)]
    assert R.floors_du_jour(p, D(2026, 11, 2), D(2026, 11, 3))[-1] == (D(2026, 11, 3), None)


def test_troll_un_jour_ne_fait_pas_l_ath():
    jours = [(D(2026, 11, k), 10.0) for k in range(1, 10)] + [(D(2026, 11, 10), 999999.0), (D(2026, 11, 11), 10.0)]
    m, ath, athd, atl, atld = R.appliquer(jours)
    assert ath == 10.0 and m[9][2] is True


def test_vrai_graal_deux_jours_de_suite_compte():
    jours = [(D(2026, 11, k), 10.0) for k in range(1, 10)] + [(D(2026, 11, 10), 400.0), (D(2026, 11, 11), 400.0)]
    m, ath, athd, atl, atld = R.appliquer(jours)
    assert ath == 400.0 and athd == D(2026, 11, 10)


def test_sous_un_dollar_jamais_meme_deux_jours():
    jours = [(D(2026, 11, 1), 5.0), (D(2026, 11, 2), 0.5), (D(2026, 11, 3), 0.5)]
    _, ath, _, atl, _ = R.appliquer(jours)
    assert atl == 5.0


def test_sans_historique_seuls_1_et_15000():
    _, ath, _, atl, _ = R.appliquer([(D(2026, 11, 1), 14000.0)])
    assert ath == 14000.0
    _, ath, _, _, _ = R.appliquer([(D(2026, 11, 1), 16000.0)])
    assert ath is None


def test_virgule_et_point():
    assert R.nombre("1,95") == 1.95 and R.nombre("15 000") == 15000.0 and R.nombre("") is None


def test_plus_long_tenu_contre_mediane_a_deux_releves():
    """2 releves (10 a minuit, 30 a 23 h) : la mediane invente 20 ; le floor tenu
    le plus longtemps est 10 (23 h contre 1 h)."""
    p = [(t(1, 0), 10.0), (t(2, 23), 30.0)]
    med = dict(R.floors_du_jour(p, None, D(2026, 11, 2), "mediane"))
    lon = dict(R.floors_du_jour(p, None, D(2026, 11, 2), "plus_long"))
    assert med[D(2026, 11, 2)] == 20.0 and lon[D(2026, 11, 2)] == 10.0


def test_plus_long_offre_d_une_minute_ne_pese_rien():
    p = [(t(1, 0), 50.0), (dt.datetime(2026, 11, 2, 10, 0), 5.0), (dt.datetime(2026, 11, 2, 10, 1), 50.0)]
    lon = dict(R.floors_du_jour(p, None, D(2026, 11, 2), "plus_long"))
    assert lon[D(2026, 11, 2)] == 50.0


def test_plus_long_pas_d_offre_toute_la_journee_case_vide():
    p = [(t(1, 0), 50.0), (dt.datetime(2026, 11, 2, 1, 0), 0.0)]
    lon = dict(R.floors_du_jour(p, None, D(2026, 11, 2), "plus_long"))
    assert lon[D(2026, 11, 2)] is None


def test_periode_couverte():
    c = R._periode_couverte
    assert c(D(2021, 1, 1), D(2022, 1, 1), True, D(2026, 11, 27)) == "non_couverte_avant_premiere_donnee"
    assert c(D(2026, 10, 15), D(2022, 1, 1), False, D(2026, 11, 27)) == "non_couverte_trou_comics"
    assert c(D(2026, 10, 15), D(2022, 1, 1), True, D(2026, 11, 27)) == "couverte"
    assert c(None, D(2022, 1, 1), True, D(2026, 11, 27)) == "date_inconnue"


def test_garder_tracker_seuils():
    g = R.garder_tracker
    assert g(500.0, "non_couverte_avant_premiere_donnee")
    assert g(500.0, "date_inconnue")
    assert not g(500.0, "couverte")
    assert not g(0.5, "non_couverte_trou_comics")
    assert not g(20000.0, "non_couverte_date_future")
    assert not g(None, "date_inconnue")


def test_lignes_changement_seulement_quand_ca_change():
    m = [(D(2026, 1, 1), 10.0, False), (D(2026, 1, 2), 10.0, False),
         (D(2026, 1, 3), 300.0, True), (D(2026, 1, 4), 300.0, False),
         (D(2026, 1, 5), None, False), (D(2026, 1, 6), None, False)]
    assert R.lignes_changement(m) == [
        (D(2026, 1, 1), "10", ""), (D(2026, 1, 3), "300", "oui"),
        (D(2026, 1, 4), "300", ""), (D(2026, 1, 5), "", "")]


def test_comparer_ecrit_le_fichier_floors_jour(tmp_path):
    import gzip as g
    prix = tmp_path / "p.csv.gz"; cat = tmp_path / "c.csv.gz"; fj = tmp_path / "fj.csv.gz"
    with g.open(prix, "wt") as f:
        f.write("veve_uuid,ts_utc,floor,listings\nabc,2026-01-01T00:00:00Z,10,\nabc,2026-01-03T00:00:00Z,12,\n")
    with g.open(cat, "wt") as f:
        f.write("veve_uuid,name,ath,ath_date,atl,atl_date,release_date,kind\nabc,X,12,2026-01-03,10,2026-01-01,,collectible\n")
    res = R.comparer(str(prix), str(cat), D(2026, 1, 5), floors_jour=str(fj))
    lignes = g.open(fj, "rt").read().splitlines()
    assert lignes[0] == "veve_uuid,date,floor,floor_suspect"
    assert lignes[1:] == ["abc,2026-01-01,10,", "abc,2026-01-03,12,"]
    assert res["floors_jour.lignes"] == 2


def test_v4_au_dessus_de_15000_jamais_meme_des_semaines():
    """CONTRAT v4 (Preda, 28/11/2026) : au-dessus de 15 000 $, jamais (Grenade Blue)."""
    jours = [(D(2025, 11, k), 3000.0) for k in range(1, 20)] + \
        [(D(2025, 11, k), 160000.0) for k in range(20, 30)] + [(D(2025, 11, 30), 1499.0)]
    _, ath, athd, atl, _ = R.appliquer(jours)
    assert ath == 3000.0 and atl == 1499.0


def test_v41_a_15000_pile_ne_compte_pas():
    """v4.1 : 15 000 $ ou plus, jamais (annonces troll au prix maximum)."""
    jours = [(D(2026, 11, k), 30.0) for k in range(1, 10)] + [(D(2026, 11, k), 15000.0) for k in range(10, 20)]
    _, ath, _, atl, _ = R.appliquer(jours)
    assert ath == 30.0 and atl == 30.0
    _, ath, _, _, _ = R.appliquer([(D(2026, 11, 1), 14999.99)])
    assert ath == 14999.99
    assert not R.garder_tracker(15000.0, "date_inconnue") and R.garder_tracker(14999.0, "date_inconnue")


def test_v42_garde_fous_ath():
    """CONTRAT v4.2 (Preda, 28/11/2026)."""
    # apres le 31/07/2026 : pas plus de 3 x la reference
    assert R.ath_plausible(3000.0, D(2026, 8, 15), 1000.0, 40.0)
    assert not R.ath_plausible(3001.0, D(2026, 8, 15), 1000.0, 40.0)
    # 2023 -> 30/07/2026 : pas plus de 100 x le floor actuel
    assert R.ath_plausible(3000.0, D(2024, 11, 8), None, 30.0)
    assert not R.ath_plausible(14999.0, D(2025, 7, 3), None, 30.0)
    # avant 2023 : aucune limite (sommets 2021-2022)
    assert R.ath_plausible(1642.0, D(2022, 1, 19), None, 7.0)
    # une vente > 20 x le floor du jour n'est pas une reference (Barbarella)
    j = {D(2026, 9, 27): 20.0}
    assert R.reference_ventes([(D(2026, 9, 27), 10000.0), (D(2026, 9, 27), 25.0)], j) == 25.0
