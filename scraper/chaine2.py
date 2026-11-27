# ⚠️ DEPOT : Leonessa2/scrapeur-veve   ·   CHEMIN : scraper/chaine2.py
"""🔗 CollectChain « chaine 2 » — la chaine repartie a zero le 19/11/2026.

CE QUI S'EST PASSE (mesure le 27/11/2026 sur l'API CollectScan)
---------------------------------------------------------------
* Le 19/11/2026 a 13:03:35 UTC, CollectChain a redemarre : bloc 1. L'ancienne
  chaine etait vers le bloc 100 500 000 ; la nouvelle en est a ~669 000.
  Meme contrat NFT, memes champs (image, metadata, token_id).
* Notre collecteur (`chain_run.py`) s'arrete des qu'un transfert a un bloc
  <= son point de reprise (~100,5 M) : depuis le 19/11, il ramene 0 transfert,
  l'etape reste verte, `chain-archive-daily` ne recoit plus rien.
* La migration a RECREE tous les jetons sur la nouvelle chaine : ~13 M
  transferts « token_minting » (methode `0x94a5dc9e`, depuis l'adresse zero,
  token_id <= 14 273 819), du 19/11 ~16 h au ~22 h 45 UTC. ⛔ CE NE SONT PAS
  DES MINTS : les compter fausserait supply, mints et grand livre.
* Les vrais mints (drops, crafts) ont repris PENDANT la migration (methode
  `0x1eb8ed88`, token_id > 14 273 819, des le 19/11 17 h 30 UTC).

CE QUE FAIT CE MODULE (aucune publication : il ecrit des fichiers locaux)
-----------------------------------------------------------------------
B. Du 20/11 00:00 UTC a la fin de la derniere journee PT complete : la
   pagination habituelle (du plus recent au plus ancien) — la migration est
   finie, elle n'y coute rien.
A. La fenetre de la migration (19/11 13:03:35 → 20/11 00:00 UTC) : impossible
   de paginer ~13 M recreations. On demande a l'API « advanced-filters » les
   seuls transferts dont la METHODE n'est pas celle de la migration (liste
   apprise en B), puis, pour chaque transaction trouvee, ses transferts
   complets (`/transactions/<hash>/token-transfers`) : meme format que B,
   avec `log_index` et l'image (donc le `veve_uuid`).
⭐⭐ NUMEROS DE BLOC : la chaine 2 repart de 1. `merge_transfers.py`
   (jetonveve) TRIE et DEDOUBLONNE l'ere CollectChain par (block, log_index) :
   un bloc 35 000 de la chaine 2 passerait AVANT l'ancienne chaine et
   pourrait ETRE PRIS POUR UN DOUBLON d'un bloc 35 000 de 2024. ⇒ on ecrit
   `block = 1 000 000 000 + bloc reel` (DECALAGE) et le bloc reel dans une
   colonne ajoutee EN FIN (`bloc_chaine2`). Lecteurs par position (merge) :
   inchanges ; lecteurs par nom (ledger, base_build) : ignorent l'ajout.
"""

from __future__ import annotations

import collections
import csv
import datetime as _dt
import gzip
import json
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from scraper import collectchain as cc

GENESE = _dt.datetime(2026, 11, 19, 13, 3, 35)          # UTC naif, bloc 1
FIN_MIGRATION = _dt.datetime(2026, 11, 20, 0, 0, 0)     # au-dela : pagination normale
DECALAGE = 1_000_000_000
METHODE_MIGRATION = "0x94a5dc9e"
TOKEN_ID_MAX_ANCIENNE = 14_273_819     # plus haut token_id de l'archive du 18/11
ADV_URL = f"{cc.API_BASE}/advanced-filters"
TX_URL = cc.API_BASE + "/transactions/{h}/token-transfers"

ENTETE = ["block", "log_index", "ts_utc", "date_pt", "kind", "category",
          "veve_uuid", "edition", "from", "to", "token_id", "bloc_chaine2"]


# ─────────────────────────────── pur ────────────────────────────────────────
def est_migration(item: Dict[str, Any]) -> bool:
    """Une recreation de la migration : methode de migration, OU mint depuis
    zero d'un token_id qui existait deja sur l'ancienne chaine pendant la
    fenetre de migration. ⭐ Deux criteres concordants (mesure du 27/11) ; un
    seul suffit a ecarter."""
    if (item.get("method") or "").lower() == METHODE_MIGRATION:
        return True
    frm = ((item.get("from") or {}).get("hash") or "").lower()
    ts = cc._parse_ts(item.get("timestamp"))
    try:
        tid = int((item.get("total") or {}).get("token_id") or 0)
    except (TypeError, ValueError):
        tid = 0
    return (frm == cc.ZERO and ts is not None and ts < FIN_MIGRATION
            and 0 < tid <= TOKEN_ID_MAX_ANCIENNE)


def ligne(rec: Dict[str, Any]) -> List[str]:
    b = rec["block"]
    return [str(DECALAGE + int(b)), str(rec["log_index"] or 0),
            rec["ts"].strftime("%Y-%m-%d %H:%M:%S"), rec["date"], rec["kind"],
            rec["category"], rec["veve_uuid"],
            "" if rec["edition"] in (None, "") else str(rec["edition"]),
            rec["from"], rec["to"], rec["token_id"], str(b)]


def par_jour(recs: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    vus = set()
    for r in recs:
        k = (r["block"], r["log_index"] or 0)
        if k in vus:                    # A et B se recouvrent a la frontiere
            continue
        vus.add(k)
        out[r["date"]].append(r)
    for j in out:
        out[j].sort(key=lambda r: (r["block"], r["log_index"] or 0))
    return dict(out)


def bilan(jours: Dict[str, List[Dict[str, Any]]], ecartes: collections.Counter,
          methodes: collections.Counter) -> Dict[str, Any]:
    tout = [r for lot in jours.values() for r in lot]
    fiches = {r["veve_uuid"] for r in tout if r["veve_uuid"]}
    return {
        "jours": {j: {"transferts": len(l),
                      "fiches": len({r["veve_uuid"] for r in l if r["veve_uuid"]}),
                      "par_type": dict(collections.Counter(r["kind"] for r in l)),
                      "premier": l[0]["ts"].strftime("%Y-%m-%d %H:%M:%S"),
                      "dernier": l[-1]["ts"].strftime("%Y-%m-%d %H:%M:%S")}
                  for j, l in sorted(jours.items())},
        "total_transferts": len(tout),
        "total_fiches": len(fiches),
        "sans_veve_uuid": sum(1 for r in tout if not r["veve_uuid"]),
        "par_categorie": dict(collections.Counter(r["category"] for r in tout)),
        "migration_ecartee": dict(ecartes),
        "methodes": dict(methodes),
    }


# ─────────────────────────────── reseau ─────────────────────────────────────
def collecte_b(jusqu_a: _dt.datetime, s=None):
    """Plus recent -> plus ancien, jusqu'a FIN_MIGRATION. Ignore >= jusqu_a
    (journee PT en cours)."""
    s = s or cc._session()
    params: Dict[str, Any] = {}
    recs, ecartes, methodes, pages = [], collections.Counter(), collections.Counter(), 0
    while True:
        d = cc._get(s, cc.TRANSFERS_URL, params)
        items = d.get("items") or []
        fin = not items
        for it in items:
            rec = cc._flatten(it)
            if rec is None:
                continue
            if rec["ts"] < FIN_MIGRATION:
                fin = True
                break
            if rec["ts"] >= jusqu_a:
                continue
            if est_migration(it):
                ecartes["B"] += 1
                continue
            methodes[(it.get("method") or "").lower()] += 1
            recs.append(rec)
        pages += 1
        if pages % 100 == 0:
            print(f"  B : {pages} pages, {len(recs)} transferts, a {recs[-1]['ts'] if recs else '-'}",
                  flush=True)
        nxt = d.get("next_page_params")
        if fin or not nxt:
            break
        params = dict(nxt)
        time.sleep(cc.PAUSE_BETWEEN_PAGES)
    print(f"B fini : {pages} pages, {len(recs)} transferts, migration ecartee {ecartes['B']}",
          flush=True)
    return recs, ecartes, methodes


def collecte_a(methodes_b: Iterable[str], s=None):
    """Fenetre de la migration, par methode (jamais `0x94a5dc9e`)."""
    s = s or cc._session()
    meth = sorted({m for m in methodes_b if m and m != METHODE_MIGRATION}
                  | {"0x1397ea85", "0x1eb8ed88"})
    base = {"transaction_types": "ERC-721",
            "token_contract_address_hashes_to_include": cc.CONTRACT,
            "methods": ",".join(meth),
            "age_from": GENESE.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "age_to": FIN_MIGRATION.strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    params, hashes, pages = dict(base), {}, 0
    while True:
        d = cc._get(s, ADV_URL, params)
        for it in d.get("items") or []:
            h = it.get("hash")
            # ⭐ `/transactions/<h>/token-transfers` rend `timestamp` et `method`
            #   A NULL (mesure du 27/11) : on les reprend ici, sinon _flatten
            #   jette tout (pas d'horodatage = transfert illisible).
            if h and h not in hashes:
                hashes[h] = (it.get("timestamp"), it.get("method"))
        pages += 1
        nxt = d.get("next_page_params")
        if not nxt or not d.get("items"):
            break
        params = dict(base, **{k: v for k, v in nxt.items() if v is not None})
        time.sleep(cc.PAUSE_BETWEEN_PAGES)
    print(f"A : {pages} pages, {len(hashes)} transactions, methodes {meth}", flush=True)
    recs, ecartes = [], collections.Counter()
    for i, (h, (ts_tx, meth_tx)) in enumerate(hashes.items(), 1):
        params = {"type": "ERC-721"}
        while True:
            d = cc._get(s, TX_URL.format(h=h), params)
            for it in d.get("items") or []:
                tok = it.get("token") or {}
                if (tok.get("address_hash") or tok.get("address") or "").lower() \
                        not in ("", cc.CONTRACT.lower()):
                    continue
                it = dict(it, timestamp=it.get("timestamp") or ts_tx,
                          method=it.get("method") or meth_tx)
                if est_migration(it):
                    ecartes["A"] += 1
                    continue
                rec = cc._flatten(it)
                if rec and GENESE <= rec["ts"] < FIN_MIGRATION:
                    recs.append(rec)
            nxt = d.get("next_page_params")
            if not nxt:
                break
            params = dict({"type": "ERC-721"}, **nxt)
        if i % 500 == 0:
            print(f"  A : {i}/{len(hashes)} transactions, {len(recs)} transferts", flush=True)
        time.sleep(cc.PAUSE_BETWEEN_PAGES)
    print(f"A fini : {len(recs)} transferts, recreations ecartees {ecartes['A']}", flush=True)
    return recs, ecartes, meth


def ecrire(jours, dossier: str) -> List[str]:
    os.makedirs(dossier, exist_ok=True)
    out = []
    for j, lot in sorted(jours.items()):
        p = os.path.join(dossier, f"transfers_daily_{j}.csv.gz")
        with gzip.open(p, "wt", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(ENTETE)
            for r in lot:
                w.writerow(ligne(r))
        out.append(p)
    return out


def main() -> int:
    dossier = os.environ.get("CHAINE2_DOSSIER", "chaine2")
    now_pt = _dt.datetime.now(cc.PT)
    jusqu_a = now_pt.replace(hour=0, minute=0, second=0, microsecond=0) \
        .astimezone(_dt.timezone.utc).replace(tzinfo=None)
    print(f"Chaine 2 : de {GENESE} a {jusqu_a} UTC (journees PT completes)", flush=True)
    rb, eb, mb = collecte_b(jusqu_a)
    ra, ea, meth = collecte_a(mb.keys())
    jours = par_jour(ra + rb)
    fichiers = ecrire(jours, dossier)
    b = bilan(jours, eb + ea, mb)
    b["methodes_demandees_fenetre_A"] = meth
    b["fichiers"] = [os.path.basename(f) for f in fichiers]
    json.dump(b, open(os.path.join(dossier, "bilan.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps(b, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
