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


def test_v4_pas_sortie_vide_et_sans_releve_seuils(tmp_path):
    """CONTRAT v4 : fiche pas encore sortie -> ATH/ATL vides ; fiche sans releve :
    valeur du tracker au-dessus de 15 000 $ -> vide."""
    import csv, gzip, datetime as dt
    from scraper import contrat_appliquer as C
    cat = tmp_path / "c.csv.gz"; prix = tmp_path / "p.csv.gz"
    with gzip.open(cat, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["uuid", "kind", "release_date", "floor", "listings", "ath", "atl", "ath_date", "atl_date"])
        w.writerow(["a", "Collectible", "05/12/2026 16:00:00", "", "", "40", "40", "2026-12-05", "2026-12-05"])
        w.writerow(["b", "Collectible", "01/01/2024", "", "", "160000", "20", "2025-01-01", "2025-01-02"])
    with gzip.open(prix, "wt", encoding="utf-8", newline="") as f:
        f.write("veve_uuid,ts_utc,floor\n")
    now = dt.datetime(2026, 11, 28, 9)
    n = C.appliquer_catalogue(str(cat), str(prix), str(tmp_path / "o"), now.date(), now, True, True, True)
    rows = {r["uuid"]: r for r in csv.DictReader(gzip.open(tmp_path / "o" / "catalogue.csv.gz", "rt", encoding="utf-8"))}
    assert rows["a"]["ath"] == "" and rows["a"]["atl"] == "" and rows["a"]["ath_brut"] == "40"
    assert rows["b"]["ath"] == "" and rows["b"]["atl"] == "20" and rows["b"]["ath_brut"] == "160000"
    assert n["fiches_pas_sorties"] == 1


def test_v41_floor_15000_ou_plus_vide(tmp_path):
    import csv, gzip, datetime as dt
    from scraper import contrat_appliquer as C
    cat = tmp_path / "c.csv.gz"; prix = tmp_path / "p.csv.gz"
    with gzip.open(cat, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["uuid", "kind", "release_date", "floor", "listings", "ath", "atl", "ath_date", "atl_date"])
        w.writerow(["a", "Collectible", "01/01/2024", "15000", "", "15000", "", "2025-01-01", ""])
        w.writerow(["b", "Collectible", "01/01/2024", "14999,99", "", "", "", "", ""])
    with gzip.open(prix, "wt", encoding="utf-8", newline="") as f:
        f.write("veve_uuid,ts_utc,floor\n")
    now = dt.datetime(2026, 11, 28, 9)
    n = C.appliquer_catalogue(str(cat), str(prix), str(tmp_path / "o"), now.date(), now, True, True, True)
    rows = {r["uuid"]: r for r in csv.DictReader(gzip.open(tmp_path / "o" / "catalogue.csv.gz", "rt", encoding="utf-8"))}
    assert rows["a"]["floor"] == "" and rows["a"]["ath"] == "" and rows["a"]["ath_brut"] == "15000"
    assert rows["b"]["floor"] == "14999,99"
    assert n["floor_vide_15000_ou_plus"] == 1 and not n.get("controle_floor_15000_ou_plus")
