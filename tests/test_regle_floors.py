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
