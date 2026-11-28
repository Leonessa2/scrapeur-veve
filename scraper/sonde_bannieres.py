"""Sonde LECTURE SEULE (28/11/2026) : d'ou recuperer les bannieres de VeVe ?
v2 : la page d'accueil de veve.me (Next.js) porte des images
`marketing_window_*` ; on lit les donnees qui les accompagnent. N'ecrit rien."""
import json, re, sys
from collections import Counter
from urllib.parse import unquote
import requests

UA = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"}


def p(*a):
    print("[bann]", *a, flush=True)


def main():
    r = requests.get("https://www.veve.me/", headers=UA, timeout=40)
    t = r.text
    p("accueil", r.status_code, len(t), "date serveur:", r.headers.get("date"), "cache:", r.headers.get("cache-control"))
    # Le flux Next.js (RSC) est echappe dans des self.__next_f.push(...)
    flux = "".join(json.loads('"' + m + '"') if True else m
                   for m in re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', t))
    p("flux_rsc_octets", len(flux))
    tout = t + "\n" + flux
    imgs = sorted(set(unquote(x) for x in re.findall(r"marketing_window[A-Za-z_]*\.[0-9a-f-]+\.[0-9a-f-]+\.[a-z]+\.(?:jpe?g|png|webp|gif)", tout)))
    p("images_marketing_window", len(imgs), Counter(i.split(".")[0] for i in imgs))
    cles = Counter()
    for m in re.finditer(r"marketing_window", flux):
        bloc = flux[max(0, m.start() - 1500): m.start() + 1500]
        cles.update(re.findall(r'"([a-zA-Z_]{3,40})":', bloc))
    p("cles_autour", cles.most_common(60))
    vus = 0
    for m in re.finditer(r"marketing_window_mobile", flux):
        if vus >= 3:
            break
        vus += 1
        p("contexte", vus, flux[max(0, m.start() - 1200): m.start() + 600].replace("\n", " "))
    for mot in ("marketingWindow", "MarketingWindow", "marketing_window", "startDate", "endDate", "startsAt", "expiresAt"):
        p("compte", mot, tout.count(mot))
    # Les requetes GraphQL nommees dans les scripts de la page
    js = sorted(set(re.findall(r'src="(/_next/static/chunks/[^"]+\.js)"', t)))
    trouve = 0
    for s in js:
        try:
            c = requests.get("https://www.veve.me" + s, headers=UA, timeout=30).text
        except Exception:
            continue
        for q in set(re.findall(r"(?:query|fragment)\s+([A-Za-z0-9_]*[Mm]arketing[A-Za-z0-9_]*)", c)):
            p("requete_js", s, q); trouve += 1
        for m in re.finditer(r"[Mm]arketing[Ww]indow", c):
            p("js_contexte", s, c[max(0, m.start() - 300): m.start() + 300].replace("\n", " ")); trouve += 1
            break
    p("js_lus", len(js), "trouvailles", trouve)
    return 0


if __name__ == "__main__":
    sys.exit(main())
