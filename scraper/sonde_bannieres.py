"""Sonde LECTURE SEULE (28/11/2026) : d'ou recuperer les bannieres de VeVe ?
Interroge l'API GraphQL publique de VeVe (meme porte que veve_detail.py) et
quelques pages, affiche ce qu'elle trouve. N'ecrit rien, ne publie rien."""
import json, re, sys
import requests
from scraper.veve_detail import GRAPHQL_URL, HEADERS

MOTS = re.compile(r"banner|carousel|feature|promo|home|spotlight|hero|announce|news|highlight|"
                  r"campaign|marketing|stor(y|ies)|curat|slide|splash|discover|explore|trend|drop|event|landing|page|tile|card", re.I)


def gql(q, v=None, op="sonde"):
    h = dict(HEADERS); h["client-operation"] = op
    try:
        r = requests.post(GRAPHQL_URL, headers=h, json={"query": q, "variables": v or {}}, timeout=40)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def main():
    p = lambda *a: print("[bann]", *a, flush=True)
    c, t = gql("{__schema{queryType{name fields{name args{name type{name kind ofType{name}}} type{name kind ofType{name kind ofType{name}}}}}}}")
    p("introspection", c, t[:300].replace("\n", " "))
    champs = []
    try:
        champs = json.loads(t)["data"]["__schema"]["queryType"]["fields"]
    except Exception:
        pass
    p("nb_champs_racine", len(champs))
    for f in champs:
        if MOTS.search(f["name"]):
            p("champ", f["name"], json.dumps(f["type"]), [a["name"] for a in f["args"]])
    # Sans introspection : deviner et lire les suggestions de GraphQL.
    for g in ["banners", "homeBanners", "banner", "featuredBanners", "carousel", "homeCarousel",
              "featured", "featuredContent", "homePage", "homeScreen", "promotions", "announcements",
              "spotlight", "heroBanners", "marketingBanners", "storeBanners", "publicBanners",
              "publicHomeBanners", "publicFeatured", "publicCarousel", "publicHome", "news", "stories",
              "publicDropCalendar", "dropCalendar", "publicStoreFront", "storeFront", "publicEvents"]:
        c, t = gql("{ %s { __typename } }" % g)
        m = re.findall(r'"message":"([^"]{0,220})', t)
        p("devine", g, c, (m[0] if m else t[:200]).replace("\n", " "))
    # Types qui parlent de bannieres (si introspection ouverte).
    c, t = gql("{__schema{types{name fields{name}}}}")
    try:
        for ty in json.loads(t)["data"]["__schema"]["types"]:
            if re.search(r"banner|carousel|promo|featur|spotlight|hero|highlight|campaign", ty["name"], re.I):
                p("type", ty["name"], [f["name"] for f in (ty["fields"] or [])][:40])
    except Exception:
        p("types", c, t[:200])
    for u in ["https://www.veve.me/", "https://www.veve.me/blog/", "https://www.veve.me/sitemap.xml",
              "https://omi.veve.me/", "https://store.veve.me/"]:
        try:
            r = requests.get(u, headers={"user-agent": "Mozilla/5.0"}, timeout=30)
            imgs = sorted(set(re.findall(r'(?:src|href)="([^"]+?\.(?:png|jpe?g|webp|gif)[^"]*)"', r.text)))
            p("page", u, r.status_code, len(r.text), r.headers.get("last-modified"), "images:", len(imgs))
            for i in imgs[:25]:
                p("   img", i)
            for s in sorted(set(re.findall(r'(?:src|href)="([^"]+\.js[^"]*)"', r.text)))[:10]:
                p("   js", s)
        except Exception as e:
            p("page", u, "erreur", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
