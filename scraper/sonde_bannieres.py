"""Sonde LECTURE SEULE (28/11/2026) : d'ou recuperer les bannieres de VeVe ?
v3 : la requete `ActiveMarketingWindows` (vue dans les scripts de veve.me)
interrogee directement sur l'API publique. N'ecrit rien, ne publie rien."""
import json, re, sys
import requests
from scraper.veve_detail import GRAPHQL_URL, HEADERS

UA = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"}
CHUNK = "https://www.veve.me/_next/static/chunks/0i2x05gihn945.js"


def p(*a):
    print("[bann]", *a, flush=True)


def main():
    js = requests.get(CHUNK, headers=UA, timeout=30).text
    i = js.find("query ActiveMarketingWindows")
    q = js[i: js.find("`", i)] if i >= 0 else ""
    p("requete", q.replace("\n", " ")[:600])
    frag = re.search(r"fragment MarketingWindowsFragment on MarketingWindow \{.*?\n\}", js, re.S)
    p("fragment_trouve", bool(frag))
    for nom in ("mobileMedia", "desktopMedia"):
        m = re.search(r"fragment (\w*Media\w*) on \w+ \{[^`]{0,200}", js)
    medias = {m.group(1): m.group(0) for m in re.finditer(r"fragment (\w+) on (Image|Media|Asset)\w* \{[^}]*\}", js)}
    p("fragments_media", list(medias)[:10])
    texte = q + "\n" + (frag.group(0) if frag else "") + "\n" + "\n".join(medias.values())
    # completer les ${...} non resolus : retire les spreads inconnus
    connus = set(re.findall(r"fragment (\w+) on", texte))
    texte = re.sub(r"\.\.\.(\w+)", lambda m: m.group(0) if m.group(1) in connus else "__typename", texte)
    p("requete_finale_octets", len(texte))
    for market in [None, "GLOBAL", "US", "DEFAULT", "COLLECTIBLES", "COMICS", "WEB", "en"]:
        h = dict(HEADERS); h["client-operation"] = "ActiveMarketingWindows"
        v = {"input": {"market": market}} if market else {"input": {}}
        try:
            r = requests.post(GRAPHQL_URL, headers=h, json={"operationName": "ActiveMarketingWindows",
                                                          "query": texte, "variables": v}, timeout=40)
        except Exception as e:
            p("api", market, "erreur", e); continue
        try:
            d = r.json()
        except Exception:
            p("api", market, r.status_code, r.text[:200]); continue
        lst = ((d.get("data") or {}).get("activeMarketingWindows")) or []
        p("api", market, r.status_code, "bannieres:", len(lst), "erreurs:", json.dumps(d.get("errors"))[:300])
        for b in lst[:12]:
            p("   ", b.get("position"), b.get("startDate"), "->", b.get("endDate"), "backup" if b.get("isBackup") else "",
              b.get("url"), json.dumps(b.get("desktopMedia"))[:160])
    # Le marche attendu : chercher dans le script l'appel avec sa valeur
    for m in re.finditer(r"ActiveMarketingWindows|market:", js):
        pass
    p("indices_market", sorted(set(re.findall(r'market[A-Za-z]*\s*[:=]\s*"([A-Z_]{2,20})"', js)))[:20])
    return 0


if __name__ == "__main__":
    sys.exit(main())
