# ⚠️ DEPOT : Leonessa2/scrapeur-veve   ·   CHEMIN : tests/test_merge_disque.py
"""Fusion « disque » == Fusion « memoire », a l'octet, sur des cas pieges.
(La meme comparaison est refaite sur les VRAIES donnees par essai-fusion.yml.)"""
import gzip
import os
import sys

from scraper import merge_transfers as M


def ecrire(p, lignes):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8", newline="") as f:
        f.write("\n".join(lignes) + "\n")


def jeu(tmp):
    s = str(tmp / "arch")
    ecrire(f"{s}/holders/h1.csv.gz", ["token_id,veve_uuid,category,edition",
                                      "10,u-a,collectible,1", "11,u-b,comic,2", "10,u-zzz,comic,9"])
    ecrire(f"{s}/imx/imx_transfers_run001.csv.gz", [
        "txn_id,txn_time_ms,date_pt,txn_type,from,to,token_id,token_address",
        "t5,1000,2021-01-01,transfer,a,b,10,x",
        "t1,3000,2021-01-01,MINT,0x0,c,11,x",
        "t2,1000,2021-01-01,transfer,c,d,11,x",       # meme ts que t5 : ordre d'apparition
        "t3,,2021-01-01,transfer,d,e,99,x",            # ts vide -> 0
        ",2000,2021-01-01,transfer,e,f,10,x"])         # sans txn_id : ignoree
    ecrire(f"{s}/imx/imx_transfers_run002.csv.gz", [
        "txn_id,txn_time_ms,date_pt,txn_type,from,to,token_id,token_address",
        "t1,9999,2021-01-02,transfer,z,z,10,x",        # doublon : la 1re occurrence gagne
        "t9,1000,2021-01-02,transfer,g,h,10,x",
        "t10,500,2021-01-02,transfer,g,h,10,x"])
    h = "block,log_index,ts_utc,date_pt,kind,category,veve_uuid,edition,from,to,token_id"
    ecrire(f"{s}/cc/transfers_daily_2026-11-18.csv.gz", [h,
        "100514303,0,2026-11-18 08:00:00,2026-11-18,market,collectible,u,1,a,b,5",
        "100514303,2,2026-11-18 08:00:01,2026-11-18,market,collectible,u,1,a,b,5",
        "100,1,2026-01-30 00:00:00,2026-01-30,mint,comic,v,3,0x0,b,6",
        "court,1"])
    ecrire(f"{s}/cc/transfers_daily_2026-11-19.csv.gz", [h + ",bloc_chaine2",
        "1000035728,2,2026-11-19 22:59:02,2026-11-19,market,collectible,w,4,a,b,7,35728",
        "100,1,2026-01-30 00:00:00,2026-01-30,mint,comic,AUTRE,3,0x0,b,6,",   # doublon : 1re gagne
        "1000035728,10,2026-11-19 22:59:03,2026-11-19,listing,collectible,w,4,a,b,7,35728"])
    return s


def fusion(tmp, s, methode, monkeypatch):
    monkeypatch.setenv("MERGE_METHODE", methode)
    out = str(tmp / f"{methode}.csv.gz")
    monkeypatch.setattr(sys, "argv", ["x", s, out])
    assert M.main() == 0
    with gzip.open(out, "rt", encoding="utf-8") as f:
        return f.read()


def test_disque_identique_a_memoire(tmp_path, monkeypatch):
    s = jeu(tmp_path)
    a = fusion(tmp_path, s, "memoire", monkeypatch)
    b = fusion(tmp_path, s, "disque", monkeypatch)
    assert a == b
    lignes = a.splitlines()
    assert len(lignes) == 1 + 6 + 5      # entete + IMX uniques + CC uniques
    assert "imx:t1" in a and "9999" not in a and "AUTRE" not in a
    # tri stable : t10 (500) puis t5 et t2 (1000, ordre d'apparition), t9, t1
    imx = [l.rsplit(",", 1)[1] for l in lignes[1:] if l.startswith("IMX")]
    assert imx == ["imx:t3", "imx:t10", "imx:t5", "imx:t2", "imx:t9", "imx:t1"]
    cc = [l.rsplit(",", 1)[1] for l in lignes[1:] if l.startswith("CollectChain")]
    assert cc == ["cc:100:1", "cc:100514303:0", "cc:100514303:2", "cc:1000035728:2", "cc:1000035728:10"]


def test_tabulation_arrete_tout():
    import pytest
    with pytest.raises(ValueError):
        M._sans_tab("a\tb")
