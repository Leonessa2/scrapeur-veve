"""Sonde SANS ECRITURE de l'onglet 📝C-BLOG (27/11/2026, pour CONTRAT.md).

Lit l'onglet une fois (get_all_records), compte, n'ecrit rien nulle part.
Sert a decrire honnetement la forme des articles dans le contrat."""
import hashlib, os, re, sys
from collections import Counter
from urllib.parse import urlparse

from scraper import blog, sheets


def source(slug: str) -> str:
    return "medium" if slug.startswith("medium-") else "ecomi" if slug.startswith("ecomi-") else "veve.me"


def main() -> int:
    gc = sheets._client()
    ws = gc.open_by_key(os.environ["SHEET_ID"]).worksheet(blog.BLOG_TAB)
    entete = ws.row_values(1)
    lignes = ws.get_all_records()
    p = lambda k, v: print(f"[blog] {k} = {v}")
    p("entete", " | ".join(entete))
    p("lignes", len(lignes))
    for r in lignes[:2] + lignes[-2:]:
        p("exemple", f"{r.get('date')!r} | {r.get('first_seen')!r} | {r.get('url')}")
    p("dates_brutes_types", dict(Counter(type(r.get('date')).__name__ for r in lignes)))
    src = Counter(); cat = Counter(); hote = Counter()
    vide = Counter(); urls = Counter(); slugs = Counter(); hach = Counter()
    tronque = 0; url_slug_diff = 0; dates_ko = 0; longueurs = []
    for r in lignes:
        s = str(r.get("slug", "")).strip(); u = str(r.get("url", "")).strip()
        c = str(r.get("content", "")).strip()
        src[source(s)] += 1; cat[f"{source(s)}:{str(r.get('category','')).strip() or '(vide)'}"] += 1
        for k in ("slug", "date", "title", "content", "url", "category"):
            if not str(r.get(k, "")).strip():
                vide[k] += 1
        if u:
            urls[u] += 1; hote[urlparse(u).netloc] += 1
            if source(s) == "veve.me" and u.rstrip("/").rsplit("/", 1)[-1] != s:
                url_slug_diff += 1
        slugs[s] += 1
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", blog._date_iso(r.get("date"))):
            dates_ko += 1
        if c:
            longueurs.append(len(c))
            if len(c) >= blog.CONTENT_MAX_CHARS:
                tronque += 1
            hach[hashlib.sha1(re.sub(r"\s+", " ", c).lower().encode()).hexdigest()] += 1
    for k, v in src.items(): p(f"source.{k}", v)
    for k, v in sorted(cat.items()): p(f"rubrique.{k}", v)
    for k, v in hote.most_common(): p(f"hote.{k}", v)
    for k in ("slug", "date", "title", "content", "url", "category"): p(f"vide.{k}", vide[k])
    p("url_en_double", sum(n - 1 for n in urls.values() if n > 1))
    p("slug_en_double", sum(n - 1 for n in slugs.values() if n > 1))
    p("veve_url_dont_fin_differe_du_slug", url_slug_diff)
    p("date_pas_AAAA-MM-JJ", dates_ko)
    p("texte_tronque_45000", tronque)
    p("texte_identique_a_un_autre", sum(n - 1 for n in hach.values() if n > 1))
    if longueurs:
        longueurs.sort(); p("texte_longueur_mediane", longueurs[len(longueurs)//2]); p("texte_longueur_min", longueurs[0])
        p("texte_moins_de_300_car", sum(1 for x in longueurs if x < 300))
    return 0


if __name__ == "__main__":
    sys.exit(main())
