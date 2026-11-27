# ⚠️ DEPOT : Leonessa2/scrapeur-veve   ·   CHEMIN : tests/test_chaine2.py
"""Chaine 2 (CollectChain repartie a zero le 19/11/2026). Zero reseau."""
import datetime as dt

from scraper import chaine2 as C

Z = "0x0000000000000000000000000000000000000000"


def item(method, frm, ts, tid):
    return {"method": method, "from": {"hash": frm}, "timestamp": ts, "total": {"token_id": str(tid)}}


def test_recreation_de_la_migration_ecartee_par_sa_methode():
    assert C.est_migration(item("0x94a5dc9e", Z, "2026-11-19T18:36:50.000000Z", 4102705))


def test_recreation_reconnue_meme_sans_methode():
    """`/transactions/<h>/token-transfers` rend method=None : le token_id suffit."""
    assert C.est_migration(item(None, Z, "2026-11-19T21:56:00.000000Z", 14114378))


def test_vrai_mint_pendant_la_migration_garde():
    """19/11 17 h 30 : drops repris PENDANT la migration, token_id neufs."""
    assert not C.est_migration(item("0x1eb8ed88", Z, "2026-11-19T17:30:00.000000Z", 14273925))


def test_vente_pendant_la_migration_gardee():
    assert not C.est_migration(item("0x1397ea85", "0xabc", "2026-11-19T22:59:02.000000Z", 8429131))


def test_mint_apres_la_migration_garde():
    assert not C.est_migration(item("0x1eb8ed88", Z, "2026-11-22T10:30:00.000000Z", 100))


def rec(b, li, ts="2026-11-20 10:00:00", date="2026-11-20"):
    return {"block": b, "log_index": li, "ts": dt.datetime.fromisoformat(ts), "date": date,
            "kind": "market", "category": "collectible", "veve_uuid": "u", "edition": 7,
            "from": "a", "to": "b", "token_id": "1"}


def test_bloc_decale_et_bloc_reel_en_fin():
    """merge_transfers trie et dedoublonne par (block, log_index) : la chaine 2
    doit passer APRES l'ancienne (~100,5 M) et ne jamais la recouvrir."""
    l = C.ligne(rec(35728, 2))
    assert l[0] == "1000035728" and int(l[0]) > 100_514_303
    assert l[-1] == "35728" and len(l) == len(C.ENTETE)
    assert C.ENTETE[:10] == ["block", "log_index", "ts_utc", "date_pt", "kind", "category",
                             "veve_uuid", "edition", "from", "to"]   # lecture par position


def test_recouvrement_a_b_dedoublonne_et_trie():
    j = C.par_jour([rec(5, 1), rec(3, 0), rec(5, 1)])
    assert [(r["block"], r["log_index"]) for r in j["2026-11-20"]] == [(3, 0), (5, 1)]
