# -*- coding: utf-8 -*-
# ⚠️ DEPOT : Leonessa2/scrapeur-veve   ·   CHEMIN : scraper/discord_calendrier.py
# Le projet vit sur 6 depots et DEUX comptes GitHub. Un fichier
# depose au mauvais endroit ne provoque aucune erreur : il dort.

"""📅 LE CALENDRIER DES DROPS, POSTE CHAQUE SAMEDI — une image par marque.

🆕 HUB-PREDABOT v2 (28/11/2026, projet Bot Discord) — deux changements,
invisibles dans le post (texte et image restent ceux d'avant, choix de Preda) :
  1. **PAS DE CALENDRIER VIDE.** Du 31/10 au 21/11, le catalogue du Sheet
     n'etait plus mis a jour (daily.yml en panne du 30/09 au 26/11) : le module
     a publie des calendriers a 3, 0, 0 et 0 drop sans rien dire. En dessous de
     `DISCORD_CALENDRIER_MIN` series (20) sur 5 semaines, il ne poste RIEN et
     sort en erreur : c'est un capteur en panne, pas une semaine calme.
  2. **UN ECHEC D'ENVOI N'EST PLUS UNE PERTE SECHE.** VeVe France a recu une
     504 de Discord 4 samedis sur 9 (10/10, 17/10, 31/10, 21/11) : son
     calendrier sautait. Apres un echec, le module regarde si le message est
     quand meme arrive (jeton du bot, lecture des derniers messages du salon) :
     arrive -> on l'adopte ; absent -> UN nouvel essai ; impossible a verifier
     -> on ne retente PAS (un doublon est pire qu'un trou) et on le dit.

Le module fabrique le PNG avec `outils/calendrier/` (le meme moteur que la
commande manuelle) et le **televerse** dans le salon de CHAQUE marque, avec son
propre webhook, sa propre langue et sa propre identite.

⚠️ ON TELEVERSE, ON NE POINTE PAS
---------------------------------
Une URL de piece jointe Discord est SIGNEE et EXPIRE (`ex/is/hm`) : au bout de
quelques heures l'image ne s'affiche plus — piege deja paye sur les images du
module `retour`. Un calendrier que les gens gardent et repartagent ne peut pas
dependre d'un lien perissable. D'ou `api.poster_fichier()`.

⚠️ DEUX MARQUES = DEUX MONDES ETANCHES
--------------------------------------
VeVe France et VeVe Insights ont chacune leur webhook, leur salon, leur langue.
**Un webhook en panne ne doit pas empecher l'autre marque de publier** : chaque
marque a son propre try, et l'etat retient la semaine publiee MARQUE PAR MARQUE.
Sans ca, un echec cote Insights ferait retenter VeVe France la semaine suivante,
ou pire, le ferait taire.

⚠️ LE GARDE-FOU DU JOUR, ET CELUI DE LA SEMAINE
-----------------------------------------------
Le hub passe TOUS LES JOURS : c'est le module qui se garde lui-meme au samedi
(`DISCORD_CALENDRIER_JOUR`, 5 = samedi), exactement comme `discord_feed` se
garde au dimanche. Et il retient la **semaine ISO** deja publiee : meme si le
hub repasse deux fois un samedi, le calendrier ne part qu'une fois.
⛔ La date NE FAIT PAS foi toute seule : c'est l'etat, commite par le workflow,
qui empeche le doublon. Si l'etat n'est pas commite, le module se repete.

Env :
  DISCORD_CALENDRIER_WEBHOOK_VEVEFRANCE    (SECRET)  · ..._VEVEINSIGHTS (SECRET)
  DISCORD_CALENDRIER_THREAD_VEVEFRANCE     (vide = salon normal, pas un forum)
  DISCORD_CALENDRIER_ROLE_VEVEFRANCE       (vide = ne ping personne)
  DISCORD_CALENDRIER_MARQUES  (defaut « vevefrance,veveinsights »)
  DISCORD_CALENDRIER_JOUR     (5 = samedi ; lun=0 … dim=6)
  DISCORD_CALENDRIER_SEMAINES (5)   · DISCORD_CALENDRIER_STATE
  DISCORD_CALENDRIER_FORCE    (true = ignore le jour ET la semaine deja publiee)
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import tempfile
import time
import traceback
from typing import Dict, List, Optional

from scraper import discord_api as api

MODULE = "calendrier"

STATE_PATH = os.environ.get("DISCORD_CALENDRIER_STATE",
                            os.path.join("data", "discord_calendrier_state.json"))
JOUR = int(os.environ.get("DISCORD_CALENDRIER_JOUR", "5"))      # 5 = samedi
SEMAINES = int(os.environ.get("DISCORD_CALENDRIER_SEMAINES", "5"))
# HUB-PREDABOT v2 : en dessous, le catalogue est en retard -> on ne poste pas.
MINIMUM = int(os.environ.get("DISCORD_CALENDRIER_MIN", "20"))
FORCE = os.environ.get("DISCORD_CALENDRIER_FORCE", "").strip().lower() == "true"
MARQUES = [m.strip() for m in
           os.environ.get("DISCORD_CALENDRIER_MARQUES",
                          "vevefrance,veveinsights").split(",") if m.strip()]

# Le texte qui accompagne l'image. Court : l'image dit tout, le texte donne le
# lien. C'est un outil promotionnel, pas un rapport.
ACCROCHES = {
    "fr": ("📅 **Le calendrier des drops** — {periode}\n"
           "{total} drops sur les 5 dernières semaines. "
           "Toutes les sorties, jour par jour."),
    "en": ("📅 **The drop calendar** — {periode}\n"
           "{total} drops over the last 5 weeks. "
           "Every release, day by day."),
}


# --------------------------------------------------------------- env par marque

def _env(prefixe: str, cle: str, defaut: str = "") -> str:
    return os.environ.get(f"DISCORD_CALENDRIER_{prefixe}_{cle.upper()}",
                          defaut).strip()


def webhook_de(cle: str) -> str:
    return _env("WEBHOOK", cle)


def thread_de(cle: str) -> str:
    return _env("THREAD", cle)


def role_de(cle: str) -> str:
    return _env("ROLE", cle)


# ------------------------------------------------------------------ garde-fous

def est_le_jour(aujourdhui: Optional[_dt.date] = None) -> bool:
    """Heure de PARIS, pas UTC.

    Le hub tourne a 07:45 UTC, soit 09:45 a Paris : le jour est deja le meme des
    deux cotes. On garde quand meme le decalage explicite — le jour ou le cron
    bougera avant 02:00 UTC, le piege serait invisible.
    """
    if aujourdhui is not None:
        return aujourdhui.weekday() == JOUR
    paris = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=2)
    return paris.weekday() == JOUR


def cle_semaine(jour: _dt.date) -> str:
    """« 2026-W31 » — la semaine ISO, cle d'anti-doublon."""
    an, sem, _ = jour.isocalendar()
    return "%d-W%02d" % (an, sem)


# ------------------------------------------------------------------- le message

def message(th, debut: _dt.date, fin: _dt.date, total: int, nom_fichier: str,
            role: str) -> Dict:
    from outils.calendrier import donnees as D
    from outils.calendrier import themes as T

    lg = T.langue_de(th)
    periode = D.libelle_periode(debut, fin, mois=T.MOIS_COURT[lg],
                                lien=T.MOTS[lg]["vers"])
    texte = ACCROCHES.get(lg, ACCROCHES["fr"]).format(periode=periode, total=total)
    if role:
        texte = f"<@&{role}>\n{texte}"
    couleur = int(th.accent.lstrip("#"), 16)
    return {
        "content": texte,
        "embeds": [{
            "color": couleur,
            # ⚠️ `attachment://` : c'est ainsi qu'un embed affiche le fichier
            # televerse dans le MEME message. Une URL http serait perissable.
            "image": {"url": "attachment://%s" % nom_fichier},
            "footer": {"text": "%s  ·  %s" % (th.site, th.discord)},
        }],
        # Par defaut on ne ping RIEN. Avec un role : CE role et lui seul.
        "allowed_mentions": api.mentions([role] if role else None),
    }


# ------------------------------------------------------------------ generation

def fabriquer(th, calendrier: Dict, dossier: str, aujourdhui: _dt.date,
              journal) -> str:
    """Le PNG de la marque. Rend le chemin du fichier ecrit.

    ⚠️ Le `calendrier` est PASSE, pas relu : les deux marques montrent les memes
    drops, seule l'apparence change. Relire le Sheet par marque ferait quatre
    lectures de 19 000 lignes la ou une suffit — et **le quota Sheets par minute
    est PARTAGE** avec le daily et les reparations.
    """
    from outils.calendrier import polices as P
    from outils.calendrier import rendu as R

    P.preparer(th.familles(), strict=True)
    svg = R.construire(calendrier, th, aujourdhui=aujourdhui, journal=journal)
    chemin = os.path.join(dossier, "calendrier-%s-%s.png"
                          % (th.cle, aujourdhui.isoformat()))
    R.en_png(svg, chemin)
    return chemin


# ------------------------------------------------- HUB-PREDABOT v2 : l'envoi

def deja_arrive(wh: str, nom: str) -> Optional[str]:
    """Apres un echec : le message est-il QUAND MEME arrive dans le salon ?

    Rend l'id du message trouve, "" s'il n'y est pas, None si on ne PEUT PAS
    savoir (pas de jeton de bot, bot absent du salon, Discord muet).

    ⚠️ Pourquoi la question se pose : une 504 de Discord veut dire « je n'ai pas
    repondu a temps », pas « je n'ai rien fait ». Le message peut etre parti
    (lecon « Read timed out » du Hub : adopter, ne pas reposter). Un webhook ne
    sait pas lister ses messages ; le BOT, lui, sait lire le salon.
    On cherche : un message de CE webhook, portant CE fichier (le nom contient
    la marque et la date du jour), parmi les 15 derniers."""
    import requests
    jeton = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not jeton or not wh:
        return None
    try:
        r = requests.get(wh.split("?")[0], timeout=20)
        if r.status_code != 200:
            return None
        info = r.json()
        salon, wid = info.get("channel_id"), str(info.get("id") or "")
        r = requests.get("https://discord.com/api/v10/channels/%s/messages"
                         % salon, params={"limit": 15}, timeout=20,
                         headers={"Authorization": "Bot " + jeton})
        if r.status_code != 200:
            return None
        for m in r.json():
            if str(m.get("webhook_id") or "") != wid:
                continue
            if any((a.get("filename") or "") == nom
                   for a in m.get("attachments") or []):
                return str(m.get("id"))
        return ""
    except Exception:                                       # noqa: BLE001
        return None


def poster_sans_doublon(wh: str, thread: str, payload: Dict, chemin: str,
                        nom: str, cle: str, pause: float = 20.0) -> Optional[str]:
    """Un envoi, et au plus UN second — jamais deux messages.

    1er essai rate -> on attend, on regarde si le message est arrive :
      * arrive        -> on adopte son id (rien n'est reposte) ;
      * pas arrive    -> un second essai, un seul ;
      * impossible de savoir -> PAS de second essai. Un trou se rattrape a la
        main ; un doublon devant tout le salon, non."""
    mid = api.poster_fichier(wh, thread, payload, chemin, nom=nom)
    if mid:
        return mid
    time.sleep(pause)
    vu = deja_arrive(wh, nom)
    if vu:
        print("calendrier/%s : l'envoi a repondu en erreur mais le message EST "
              "arrive (%s) — adopte, rien n'est reposte." % (cle, vu), flush=True)
        return vu
    if vu is None:
        print("calendrier/%s : envoi en erreur, et impossible de verifier s'il "
              "est arrive (jeton du bot absent ou salon illisible) — on ne "
              "retente PAS, pour ne pas risquer un doublon. A verifier a la "
              "main dans le salon." % cle, file=sys.stderr)
        return None
    print("calendrier/%s : envoi en erreur et message absent du salon — un "
          "second essai, le dernier." % cle, flush=True)
    return api.poster_fichier(wh, thread, payload, chemin, nom=nom)


# ------------------------------------------------------------------------ main

def _publier_une_marque(cle: str, grille: Dict, dossier: str,
                        aujourdhui: _dt.date, state: Dict, journal) -> int:
    from outils.calendrier import themes as T

    if cle not in T.THEMES:
        print("calendrier : marque inconnue %r — connues : %s"
              % (cle, ", ".join(sorted(T.THEMES))), file=sys.stderr)
        return 1
    th = T.THEMES[cle]
    wh, thread, role = webhook_de(cle), thread_de(cle), role_de(cle)
    empreinte = api.empreinte(wh, thread)
    memoire = state.get(cle) or {}
    semaine = cle_semaine(aujourdhui)

    if (not FORCE and memoire.get("semaine") == semaine
            and memoire.get("empreinte") == empreinte):
        print("calendrier/%s : la semaine %s est deja publiee — on ne reposte "
              "pas." % (cle, semaine), flush=True)
        return 0

    chemin = fabriquer(th, grille["calendrier"], dossier, aujourdhui, journal)
    nom = os.path.basename(chemin)
    payload = message(th, grille["debut"], grille["fin"], grille["total"],
                      nom, role)

    if not wh:
        # ⚠️ En simulation on N'ECRIT PAS l'etat : sinon un essai « brulerait »
        # la semaine et le vrai run du samedi se tairait. (Regle deja posee sur
        # le module feed.)
        print("\n[SIMULATION — pas de webhook pour %s]" % cle, flush=True)
        print(payload["content"], flush=True)
        print("image : %s (%d Ko)" % (chemin, os.path.getsize(chemin) // 1024),
              flush=True)
        return 0

    mid = poster_sans_doublon(wh, thread, payload, chemin, nom, cle)
    if not mid:
        print("calendrier/%s : ECHEC de la publication — l'etat n'est PAS "
              "ecrit, on retentera." % cle, file=sys.stderr)
        return 1
    state[cle] = {"semaine": semaine, "empreinte": empreinte, "message": mid}
    print("calendrier/%s : publie (message %s, %d Ko)."
          % (cle, mid, os.path.getsize(chemin) // 1024), flush=True)
    api.souffler()
    return 0


def run() -> int:
    t0 = time.time()
    aujourdhui = _dt.date.today()

    if not FORCE and not est_le_jour():
        print("calendrier : on ne poste que le jour %d (samedi) — rien a faire. "
              "(DISCORD_CALENDRIER_FORCE=true pour forcer.)" % JOUR, flush=True)
        return 0

    if not os.environ.get("SHEET_ID", "").strip():
        print("SHEET_ID env var is not set.", file=sys.stderr)
        return 2

    from outils.calendrier import donnees as D
    from outils.calendrier import visuels as V
    journal = V.Journal()

    # ⭐ UNE SEULE lecture du Sheet pour TOUTES les marques (cf. `fabriquer`).
    debut, fin = D.fenetre(aujourdhui, semaines=SEMAINES)
    lignes = D.lignes_sheet()
    calendrier = D.grouper(lignes, debut, fin)
    grille = {"calendrier": calendrier, "debut": debut, "fin": fin,
              "total": sum(j.nb for j in calendrier.values())}
    print("calendrier : fenetre %s → %s · %d drops (maille serie)"
          % (debut, fin, grille["total"]), flush=True)

    # HUB-PREDABOT v2 — garde-fou des donnees : un calendrier presque vide est
    # le signe d'un catalogue en retard, pas d'un mois calme (vecu du 31/10 au
    # 21/11 : 3, 0, 0 et 0 drop publies).
    if grille["total"] < MINIMUM:
        print("::error::calendrier : seulement %d serie(s) sur %d semaines "
              "(minimum %d) — le catalogue du Sheet est sans doute en retard. "
              "RIEN n'est poste, aucune semaine n'est marquee. "
              "(DISCORD_CALENDRIER_MIN pour changer le seuil.)"
              % (grille["total"], SEMAINES, MINIMUM), file=sys.stderr)
        return 1

    # ⚠️ `load_state` avec un webhook vide SAUTE le controle d'empreinte : il y a
    # DEUX webhooks ici, l'empreinte est donc verifiee marque par marque, plus
    # bas. Un seul controle global effacerait la memoire des deux marques des
    # que l'une change de salon.
    state = api.load_state(STATE_PATH, "", "")
    codes: Dict[str, int] = {}
    dossier = tempfile.mkdtemp(prefix="calendrier-")

    for cle in MARQUES:
        try:
            codes[cle] = _publier_une_marque(cle, grille, dossier, aujourdhui,
                                             state, journal)
        except Exception:                                   # noqa: BLE001
            # Une marque qui tombe ne doit pas emporter l'autre.
            traceback.print_exc()
            codes[cle] = 1

    # ⚠️ On n'ecrit l'etat QUE si une marque a REELLEMENT publie. Un run en
    # simulation (webhook absent) rendait 0 lui aussi : ecrire l'etat sur ce
    # seul critere aurait fini par « bruler » une semaine le jour ou la logique
    # d'anti-doublon aurait change. Le critere est la publication, pas le succes.
    if any((state.get(cle) or {}).get("semaine") == cle_semaine(aujourdhui)
           for cle in MARQUES):
        api.save_state(STATE_PATH, state, "", "")
    print("calendrier : %s · %s · %.1f s"
          % (codes, journal.resume(), time.time() - t0), flush=True)
    return 0 if all(c == 0 for c in codes.values()) else 1


if __name__ == "__main__":
    sys.exit(run())
