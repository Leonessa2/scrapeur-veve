"""CONTRAT.md (27/11/2026) : l'adresse d'origine d'un article ne change jamais."""
from scraper import blog


class FauxOnglet:
    row_count = 2
    def __init__(self, lignes): self.lignes = lignes; self.ecrit = None
    def get_all_records(self): return self.lignes
    def clear(self): pass
    def update(self, range_name, values, value_input_option): self.ecrit = values
    def freeze(self, rows): pass
    def format(self, *a): pass


def test_url_d_origine_gardee(monkeypatch):
    ws = FauxOnglet([{"slug": "mon-article", "date": "2026-01-02", "title": "A",
                      "url": "https://www.veve.me/blog/news/mon-article",
                      "first_seen": "x", "content": "texte"}])
    monkeypatch.setattr(blog, "_open", lambda sid: (None, ws))
    blog.sync_blog([{"slug": "mon-article", "title": "A bis",
                     "url": "https://www.veve.me/blog/updates/mon-article"}], "id")
    entete, ligne = ws.ecrit[0], ws.ecrit[1]
    assert ligne[entete.index("url")] == "https://www.veve.me/blog/news/mon-article"
    assert ligne[entete.index("title")] == "A bis"


def test_nouvel_article_prend_son_adresse(monkeypatch):
    ws = FauxOnglet([])
    monkeypatch.setattr(blog, "_open", lambda sid: (None, ws))
    blog.sync_blog([{"slug": "neuf", "url": "https://www.veve.me/blog/news/neuf"}], "id")
    assert ws.ecrit[1][ws.ecrit[0].index("url")] == "https://www.veve.me/blog/news/neuf"
