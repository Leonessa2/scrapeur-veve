import csv, datetime as dt, gzip, json

from scraper import contrat_appliquer as C

D = dt.date


def _ecrire(tmp, cat_rows, prix_rows):
    cat = tmp / "c.csv.gz"; prix = tmp / "p.csv.gz"
    with gzip.open(cat, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["uuid", "kind", "name", "release_date", "floor", "listings",
                                          "ath", "atl", "ath_date", "atl_date"])
        w.writeheader(); w.writerows(cat_rows)
    with gzip.open(prix, "wt", newline="") as f:
        f.write("veve_uuid,ts_utc,floor,listings\n")
        for r in prix_rows:
            f.write(",".join(r) + "\n")
    return str(cat), str(prix)


def _lire(path):
    with gzip.open(path, "rt") as f:
        return list(csv.DictReader(f))


def test_tout_eteint_ne_touche_rien(tmp_path, monkeypatch):
    for v in ("CONTRAT_OFFRES_VIDES", "CONTRAT_FLOORS_JOUR", "CONTRAT_ATH_ATL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("sys.argv", ["x", "a", "b", str(tmp_path / "o")])
    assert C.main() == 0
    assert not (tmp_path / "o").exists()


def test_offres_vides_seules(tmp_path):
    cat, prix = _ecrire(tmp_path, [{"uuid": "a", "kind": "collectible", "floor": "10", "listings": "0",
                                    "ath": "50", "atl": "5", "ath_date": "2021-01-01", "atl_date": "2021-02-01"}], [])
    n = C.appliquer_catalogue(cat, prix, str(tmp_path / "o"), D(2026, 11, 28), dt.datetime(2026, 11, 28, 7),
                              True, False, False)
    r = _lire(tmp_path / "o" / "catalogue.csv.gz")[0]
    assert r["listings"] == "" and r["ath"] == "50" and "ath_brut" not in r
    assert n["offres_videes"] == 1


def test_ath_atl_regle_et_bruts(tmp_path):
    # historique couvert depuis le 01/01/2026 ; tracker ATH 900 date du 15/03/2026 (couverte) -> remplace
    cat, prix = _ecrire(tmp_path, [{"uuid": "a", "kind": "collectible", "floor": "12", "listings": "3",
                                    "ath": "900", "atl": "1.5", "ath_date": "2026-03-15", "atl_date": "2025-06-01",
                                    "release_date": ""}],
                        [("a", "2026-01-01T00:00:00Z", "10", "1"), ("a", "2026-03-15T00:00:00Z", "20", "1"),
                         ("a", "2026-03-15T00:01:00Z", "10", "1")])
    n = C.appliquer_catalogue(cat, prix, str(tmp_path / "o"), D(2026, 11, 28), dt.datetime(2026, 11, 28, 7),
                              False, True, True)
    r = _lire(tmp_path / "o" / "catalogue.csv.gz")[0]
    assert r["ath_brut"] == "900" and r["ath"] == "12"          # 20 n'a tenu qu'une minute
    assert r["atl"] == "1.5" and r["atl_date"] == "2025-06-01"   # avant notre 1re donnee : tracker garde
    assert r["listings"] == "3"                                  # offres non touchees
    fj = _lire(tmp_path / "o" / "floors_jour.csv.gz")
    assert fj[0] == {"veve_uuid": "a", "date": "2026-01-01", "floor": "10", "floor_suspect": ""}
    meta = json.load(open(tmp_path / "o" / "floors_jour.json"))
    assert meta["lignes"] == len(fj) and n["floors_jour.lignes"] == len(fj)


def test_tracker_hors_seuils_remplace(tmp_path):
    cat, prix = _ecrire(tmp_path, [{"uuid": "a", "kind": "collectible", "floor": "10", "listings": "",
                                    "ath": "10000042", "atl": "10", "ath_date": "2020-01-01", "atl_date": "2026-01-01"}],
                        [("a", "2026-01-01T00:00:00Z", "10", "")])
    C.appliquer_catalogue(cat, prix, str(tmp_path / "o"), D(2026, 11, 28), dt.datetime(2026, 11, 28, 7),
                          False, False, True)
    r = _lire(tmp_path / "o" / "catalogue.csv.gz")[0]
    assert r["ath"] == "10" and r["ath_brut"] == "10000042"
