"""Sonde LECTURE SEULE (28/11/2026, CONTRAT.md section 2) : combien de cases
« nombre d'offres » passeraient a vide ? Compte les valeurs non vides de la
colonne `listings` dans les fichiers donnes. N'ecrit rien."""
import csv, gzip, sys
from collections import Counter


def compter(chemin: str) -> Counter:
    ouvrir = gzip.open if chemin.endswith(".gz") else open
    c = Counter()
    with ouvrir(chemin, "rt", encoding="utf-8", newline="") as f:
        lec = csv.DictReader(f)
        col = next((k for k in (lec.fieldnames or []) if k.strip().lower() == "listings"), None)
        c["colonne_trouvee"] = 1 if col else 0
        cle = next((k for k in (lec.fieldnames or []) if k in ("veve_uuid", "uuid")), None)
        fiches, fiches_val = set(), set()
        for r in lec:
            c["lignes"] += 1
            v = (r.get(col) or "").strip() if col else ""
            u = (r.get(cle) or "").strip().lower() if cle else ""
            fiches.add(u)
            if v == "":
                c["deja_vide"] += 1
                continue
            c["non_vide"] += 1
            c["zero" if v in ("0", "0.0") else "plus_de_zero"] += 1
            fiches_val.add(u)
        c["fiches"] = len(fiches)
        c["fiches_avec_une_valeur"] = len(fiches_val)
    return c


if __name__ == "__main__":
    for chemin in sys.argv[1:]:
        try:
            for k, v in sorted(compter(chemin).items()):
                print(f"[offres] {chemin} {k} = {v}")
        except FileNotFoundError:
            print(f"[offres] {chemin} absent")
