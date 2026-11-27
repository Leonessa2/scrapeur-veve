# ⚠️ DEPOT : Leonessa2/scrapeur-veve   ·   CHEMIN : tests/test_chaine2_quotidien.py
"""Chaine 2 dans le collecteur QUOTIDIEN (chain_run + collectchain). Zero reseau."""
import csv
import datetime as dt
import gzip
import os

import pytest

from scraper import chain_run as CR
from scraper import collectchain as cc

Z = cc.ZERO


def item(block, li, ts, frm, to, tid, method="0x1397ea85", image="collectible_type_image.11111111-2222-3333-4444-555555555555"):
    return {"block_number": block, "log_index": li, "timestamp": ts, "method": method,
            "from": {"hash": frm}, "to": {"hash": to},
            "total": {"token_id": str(tid), "token_instance": {"image_url": image, "metadata": {"name": "X"}}}}


def test_stock_mint_sans_metadonnee():
    r = cc._flatten(item(500000, 0, "2026-11-26T09:00:00.000000Z", Z, cc.VEVE_OFFICIAL, 14288000, "0x1eb8ed88", image=""))
    r["category"] = "unknown"
    assert cc.est_stock(r)


def test_vrai_mint_pas_stock():
    r = cc._flatten(item(500000, 0, "2026-11-26T09:00:00.000000Z", Z, "0xacheteur", 14288001, "0x1eb8ed88"))
    assert not cc.est_stock(r)


def test_ancienne_chaine_jamais_stock_ni_decalee():
    r = cc._flatten(item(100514303, 0, "2026-11-18T09:00:00.000000Z", Z, "0xa", 14273000, "x", image=""))
    r["category"] = "unknown"
    assert not cc.est_stock(r)
    assert cc.bloc_archive(r) == (100514303, "")


def test_bloc_chaine2_decale_d_un_milliard():
    r = cc._flatten(item(35728, 2, "2026-11-19T22:59:02.000000Z", "0xa", "0xb", 8429131))
    assert cc.bloc_archive(r) == (1_000_035_728, "35728")


def test_fetch_ecarte_migration_et_met_le_stock_a_part(monkeypatch):
    page = {"items": [
        item(600000, 1, "2026-11-26T10:00:00.000000Z", "0xa", "0xb", 1000),                       # marche
        item(599999, 0, "2026-11-26T09:59:00.000000Z", Z, cc.VEVE_OFFICIAL, 14288500, "0x1eb8ed88", image=""),  # stock
        item(20000, 0, "2026-11-19T18:36:50.000000Z", Z, "0xc", 4102705, "0x94a5dc9e"),           # migration
    ], "next_page_params": None}
    monkeypatch.setattr(cc, "_get", lambda s, u, p: page)
    monkeypatch.setattr(cc.time, "sleep", lambda *_: None)
    recs, meta = cc.fetch_transfers(dt.datetime(2026, 11, 1))
    assert [r["block"] for r in recs] == [600000]
    assert meta["migration_ecartee"] == 1 and len(meta["stock"]) == 1
    assert meta["newest_block"] == 600000           # point de reprise en numero REEL


def lire(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_archive_ecrit_bloc_decale_et_colonne_en_fin(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAIN_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.chdir(tmp_path)
    r = cc._flatten(item(35728, 2, "2026-11-20T12:00:00.000000Z", "0xa", "0xb", 8429131))
    CR._archive_records([r], "2026-11-18")
    l = lire(tmp_path / "archive" / "transfers_daily_2026-11-20.csv.gz")
    assert l[0] == CR.ARCHIVE_HEADER and l[0][:10] == ["block", "log_index", "ts_utc", "date_pt", "kind",
                                                       "category", "veve_uuid", "edition", "from", "to"]
    assert l[1][0] == "1000035728" and l[1][-1] == "35728"


def test_stock_range_a_part_sous_un_nom_que_ledger_ne_ramasse_pas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = cc._flatten(item(599999, 0, "2026-11-26T09:59:00.000000Z", Z, cc.VEVE_OFFICIAL, 14288500, "0x1eb8ed88", image=""))
    CR._archive_stock([r], "2026-11-18")
    noms = os.listdir(tmp_path / "archive_stock")
    assert noms == ["stock_mints_2026-11-26.csv.gz"]
    assert not ("transfers" in noms[0] and "daily" in noms[0])
