"""
CollectChain tracker — entry point.

Modes (env CHAIN_MODE):
    backfill — fetch the last CHAIN_BACKFILL_DAYS (default 31) days of
               transfers and REPLACE the ChainActivity tab. Run once, or
               whenever you want to rebuild from scratch. ~30-60 min.
    daily    — incremental: fetch only transfers newer than the checkpoint
               stored in ChainMeta, append, prune old rows, recompute stats.

Env:
    SHEET_ID              spreadsheet id (same as the catalogue sheet)
    CHAIN_MODE            backfill | daily          (default: daily)
    CHAIN_BACKFILL_DAYS   days for backfill mode    (default: 31)
    CHAIN_ARCHIVE         "true" (defaut) = archiver les journees PT completes
                          traitees en archive/transfers_daily_<date>.csv.gz
                          (continuite de l'archive du scan profond ; le workflow
                          les uploade dans la Release chain-archive-daily)
    CHAIN_ARCHIVE_DIR     dossier de sortie (defaut "archive")
"""

from __future__ import annotations

import csv
import datetime as _dt
import gzip
import os
import sys
import time

from scraper import collectchain as cc
from scraper import chain_sheets as cs

# Colonnes de l'archive des transferts — IDENTIQUES a celles du scan profond
# (wallet_scan / Release chain-archive du repo astronema) pour que ledger.py
# lise les deux sources uniformement.
#
# 🆕 11e colonne (05/08/2026) — `token_id`, L'IDENTITE DE L'EXEMPLAIRE.
# ⭐⭐⭐ PHASE 2 DE « COLLECTCHAIN D'ABORD ». `collectchain._flatten` PRODUIT
# deja `token_id` (`str(total.get("token_id") or "")`) : la donnee survivait a
# la collecte et mourait ICI, a l'ecriture. Le second endroit ne ressemble pas
# au premier, donc on ne l'y cherchait pas.
# ⭐⭐ UNE DONNEE QUI SURVIT A LA COLLECTE PEUT ENCORE MOURIR AU STOCKAGE.
#
# LE CHIFFRE, MESURE LE 05/08 sur Archive/base/veve.duckdb :
#     ere imx : 24 501 297 / 24 501 301 transferts portent un token_id (100 %)
#     ere cc  :          0 /  7 130 601                                (  0 %)
# La colonne EXISTE DEJA en aval : `base_build.py` ecrit
# `CAST(NULL AS BIGINT) AS token_id` pour l'ere CC. Le contenant etait pret,
# c'est la source qui ne le remplissait pas — il n'y a rien a creer plus loin.
#
# ⛔ AJOUTEE EN FIN, ET C'EST LA CONDITION DE SURETE. Les trois lecteurs de ce
# format n'ont pas la meme discipline :
#     ledger.py           csv.DictReader   -> par NOM,      ignore l'ajout
#     base_build.py       read_csv_auto    -> par NOM,      ignore l'ajout
#     merge_transfers.py  p[0]..p[9]       -> par POSITION, garde `len(p) < 10`
# Le troisieme casserait si on inserait au milieu — et il vit dans un AUTRE
# depot (Leonessa2/jetonveve) : il ne casserait donc pas ici, il casserait
# ailleurs, plus tard, sans rien dire.
# ⭐⭐ UN FORMAT PARTAGE PAR TROIS DEPOTS NE SE MODIFIE QU'EN FIN : CE QUI LIT
# PAR POSITION NE SE PLAINT JAMAIS, IL SE DECALE.
#
# ⚠️ CE QUE CE LOT NE FAIT PAS : le scan PROFOND
# (`astronema/wallet_scan.py`) ecrit le meme format et n'a pas encore la
# colonne. Les deux sources restent lisibles ensemble (lecture par nom, valeur
# vide toleree), mais l'archive ancienne ne se remplit pas retroactivement :
# seules les journees ecrites APRES ce lot portent un token_id. Ecrit ici pour
# que ca ne se redecouvre pas dans six mois comme une anomalie.
ARCHIVE_HEADER = ["block", "log_index", "ts_utc", "date_pt", "kind", "category",
                  "veve_uuid", "edition", "from", "to", "token_id", "bloc_chaine2"]
# 🔗 12e colonne (27/11/2026) — `bloc_chaine2` : le numero de bloc REEL de la
# chaine 2 (CollectChain repartie a zero le 19/11). La colonne `block` porte
# alors 1 000 000 000 + ce numero (voir collectchain.bloc_archive). Vide pour
# l'ancienne chaine. ⛔ Toujours EN FIN, meme raison que `token_id` ci-dessus.
# Lecteurs verifies le 27/11 : merge_transfers (position p[0..9]), ledger.py
# et pouls.mjs de veveprice (par nom), base_build (DuckDB, essaye sur des
# fichiers a 10/11/12 colonnes) — aucun ne casse.
STOCK_HEADER = ["block", "log_index", "ts_utc", "date_pt", "kind", "from", "to",
                "token_id", "bloc_chaine2"]


def _archive_records(records, min_complete_day: str):
    """CONTINUITE DE L'ARCHIVE : ecrit les transferts traites dans
    archive/transfers_daily_<date_pt>.csv.gz — UN fichier par journee PT.

    Idempotent : re-traiter une journee (backfill) reecrit le meme fichier,
    remplace dans la Release par --clobber. `min_complete_day` = journee PT
    contenant le cutoff, potentiellement PARTIELLE -> exclue, ainsi que tout
    ce qui est plus ancien (on n'archive que des journees completes ; le scan
    profond ou un backfill plus large les fournit). Les chevauchements avec le
    scan profond sont deduplique par (block, log_index) dans ledger.replay.
    Retourne {date_pt: nb_lignes}.
    """
    if os.environ.get("CHAIN_ARCHIVE", "true").strip().lower() != "true":
        return {}
    outdir = os.environ.get("CHAIN_ARCHIVE_DIR", "archive")
    by_day = {}
    for r in records:
        if r["date"] <= min_complete_day:
            continue                      # journee du cutoff = partielle
        by_day.setdefault(r["date"], []).append(r)
    if not by_day:
        return {}
    os.makedirs(outdir, exist_ok=True)
    counts = {}
    for day, recs in sorted(by_day.items()):
        recs.sort(key=lambda r: (r["ts"], r["block"] or 0, r["log_index"] or 0))
        path = os.path.join(outdir, f"transfers_daily_{day}.csv.gz")
        with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(ARCHIVE_HEADER)
            for r in recs:
                # ⭐ `.get()` et pas `r["token_id"]` : `_archive_records`
                # accepte n'importe quel record au format `_flatten`, y compris
                # celui d'une COPIE plus ancienne du collecteur (astronema,
                # paolo). Un KeyError ici arreterait l'archivage d'une journee
                # entiere pour une colonne d'appoint — le prix est sans commune
                # mesure avec le gain.
                bloc, bloc2 = cc.bloc_archive(r)
                w.writerow([bloc, r["log_index"] or 0,
                            r["ts"].strftime("%Y-%m-%d %H:%M:%S"), r["date"],
                            r["kind"], r["category"], r["veve_uuid"],
                            r["edition"], r["from"], r["to"],
                            r.get("token_id") or "", bloc2])
        counts[day] = len(recs)
    return counts


def _archive_stock(stock, min_complete_day: str):
    """Mints « stock » de la chaine 2 (sans metadonnee, crees chez VeVe) :
    gardes A PART dans archive_stock/stock_mints_<date_pt>.csv.gz, jamais dans
    l'archive des transferts (decision de Preda, 27/11). ⛔ Le nom ne contient
    ni « transfers » ni « daily » : ledger.py ramasse `*transfers*daily*`."""
    by_day = {}
    for r in stock or []:
        if r["date"] > min_complete_day:
            by_day.setdefault(r["date"], []).append(r)
    if not by_day:
        return {}
    os.makedirs("archive_stock", exist_ok=True)
    counts = {}
    for day, recs in sorted(by_day.items()):
        recs.sort(key=lambda r: (r["ts"], r["block"] or 0, r["log_index"] or 0))
        with gzip.open(os.path.join("archive_stock", f"stock_mints_{day}.csv.gz"),
                       "wt", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(STOCK_HEADER)
            for r in recs:
                bloc, bloc2 = cc.bloc_archive(r)
                w.writerow([bloc, r["log_index"] or 0, r["ts"].strftime("%Y-%m-%d %H:%M:%S"),
                            r["date"], r["kind"], r["from"], r["to"],
                            r.get("token_id") or "", bloc2])
        counts[day] = len(recs)
    return counts


def main() -> int:
    sheet_id = os.environ.get("SHEET_ID", "").strip()
    if not sheet_id:
        print("SHEET_ID env var is not set.", file=sys.stderr)
        return 2

    mode = os.environ.get("CHAIN_MODE", "daily").strip().lower()
    backfill_days = int(os.environ.get("CHAIN_BACKFILL_DAYS", "31"))
    t0 = time.time()
    summary = {"mode": mode, "status": "OK", "note": ""}

    try:
        totals = cc.chain_totals()
        print(f"Chain totals: {totals}", flush=True)
    except Exception as e:
        totals = None
        print(f"stats endpoint warning: {e}", flush=True)

    # Only ever process fully-finished PACIFIC days (les journees sont decoupees
    # en PT, le fuseau metier VeVe) : tout ce qui est a/apres minuit PT du jour
    # courant est ignore et sera traite demain.
    now_pt = _dt.datetime.now(cc.PT)
    pt_midnight = now_pt.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = pt_midnight.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    last_complete_day = now_pt.date() - _dt.timedelta(days=1)

    records_archive = None          # rattrapage2 : sans les journees deja publiees
    try:
        if mode == "backfill":
            cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=backfill_days)
            print(f"BACKFILL: fetching transfers {cutoff:%Y-%m-%d} → "
                  f"{last_complete_day} (complete days only)...", flush=True)
            records, meta = cc.fetch_transfers(cutoff, until=today_start)
            rows = cc.aggregate_daily(records)
            added = cs.append_activity(sheet_id, rows, replace=True)
            cs.append_items(sheet_id, cc.aggregate_items(records), replace=True)
            pruned = 0
        elif mode == "rattrapage2":
            # 🔗 RATTRAPAGE CHAINE 2 (27/11/2026, go de Preda) : une seule fois,
            # a la main (`chaine2-rattrapage.yml`). Collecte du 19/11 13:03 UTC
            # a la fin de la veille PT (scraper/chaine2.py : sans recreations
            # de la migration), puis meme suite que `daily` : Sheet, archive,
            # registre, point de reprise en numeros REELS de la chaine 2.
            from scraper import chaine2 as c2
            # ⛔ UNE SEULE FOIS : si le point de reprise est deja sur la chaine 2,
            #   le rattrapage est fait — le relancer doublerait les lignes du Sheet.
            deja_pt = cs.read_checkpoint(sheet_id)
            tete = cc.tete_chaine()
            if deja_pt and tete and deja_pt[0] <= tete:
                raise RuntimeError(f"Rattrapage DEJA FAIT : point de reprise {deja_pt} "
                                   f"sur la chaine 2 (dernier bloc {tete}). Rien a faire.")
            rb, eb, mb = c2.collecte_b(today_start)
            ra, ea, _m = c2.collecte_a(mb.keys())
            tout = [r for lot in c2.par_jour(ra + rb).values() for r in lot]
            stock = [r for r in tout if cc.est_stock(r)]
            records = [r for r in tout if not cc.est_stock(r)]
            plus = max(tout, key=lambda r: (r["block"], r["log_index"] or 0)) if tout else None
            meta = {"pages": 0, "count": len(records), "skipped_current_day": 0,
                    "newest_block": plus["block"] if plus else None,
                    "newest_log_index": (plus["log_index"] or 0) if plus else None,
                    "newest_ts": plus["ts"].strftime("%Y-%m-%d %H:%M:%S") if plus else "",
                    "migration_ecartee": sum(eb.values()) + sum(ea.values()),
                    "stock": stock}
            print(f"RATTRAPAGE CHAINE 2 : {len(records)} transferts, {len(stock)} mints "
                  f"stock mis a part, {meta['migration_ecartee']} recreations ecartees.",
                  flush=True)
            # ⛔ Les journees DEJA dans la release ne sont pas reecrites.
            deja = {j.strip() for j in os.environ.get("CHAIN2_JOURS_DEJA", "").split(",")
                    if j.strip()}
            rows = cc.aggregate_daily(records)
            added = cs.append_activity(sheet_id, rows)
            cs.append_items(sheet_id, cc.aggregate_items(records))
            pruned = cs.prune_activity(sheet_id) + cs.prune_items(sheet_id)
            # ⭐ Point de reprise pose TOUT DE SUITE apres le Sheet : si la suite
            #   echoue, une relance ne rajoute pas une 2e fois les memes lignes.
            if meta.get("newest_block"):
                cs.write_meta(sheet_id, meta, totals)
            cutoff = _dt.datetime(2026, 11, 18, 12, 0)      # journee PT 18/11 exclue
            records_archive = [r for r in records if r["date"] not in deja]
        else:
            checkpoint = cs.read_checkpoint(sheet_id)
            # 🔗 GARDE DU 27/11/2026 : un point de reprise PLUS GRAND que le
            # dernier bloc de la chaine = la chaine est repartie a zero (19/11).
            # Avant, l'etape ramenait 0 transfert et restait VERTE huit jours.
            tete = cc.tete_chaine()
            if checkpoint and tete and checkpoint[0] > tete:
                raise RuntimeError(
                    f"CHAINE REPARTIE A ZERO : point de reprise {checkpoint[0]} > dernier "
                    f"bloc {tete}. Lancer chaine2-rattrapage.yml (une fois), pas ce mode.")
            cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=cs.RETENTION_DAYS)
            print(f"DAILY: checkpoint={checkpoint}, safety cutoff={cutoff:%Y-%m-%d}, "
                  f"last complete day={last_complete_day}", flush=True)
            if checkpoint is None:
                print("No checkpoint found — did you run the backfill? "
                      "Falling back to the last 2 days only.", flush=True)
                cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=2)
            records, meta = cc.fetch_transfers(cutoff, checkpoint=checkpoint,
                                               until=today_start)
            # ⭐⭐ UN ZERO LEGITIME ET UN ZERO CASSE S'IMPRIMENT PAREIL.
            #
            # Constate le 30/07/2026 sur `daily` #122 : `Fetched 0 transfers over
            # 123 pages`, `activity_rows_added: 0`, et `collectscan` 🟢 sur 124
            # requetes sans une erreur. La source allait bien, le filtre mangeait
            # tout — et rien dans le log ne disait POURQUOI.
            #
            # La cause n'est ni un bug ni du retard de cron : c'est un DOUBLON
            # d'ordonnancement, documente depuis le 13/07 dans l'en-tete de
            # `chain-catchup.yml`. Une journee PT se termine a 07:00 UTC ; le
            # rattrapage tourne a 07:30 UTC (00:30 PT du jour D) et vise minuit
            # PT du jour D. Le `daily` du LENDEMAIN a 02:15 UTC est a 19:15 PT du
            # jour D : il vise le MEME `until`, ~19 h plus tard. Le checkpoint est
            # deja a la frontiere, donc il n'a rien a faire — TOUS LES JOURS.
            #
            # ⭐ On ne retire pas l'etape (decision de Preda, 30/07) : on la fait
            # PARLER. Un no-op qui s'annonce coute 123 pages ; un no-op muet coute
            # une enquete a chaque fois qu'on relit le log.
            if not records:
                saut = meta.get("skipped_current_day", 0)
                if checkpoint and saut:
                    print(f"  ℹ️ ZERO ATTENDU, pas une panne : le checkpoint "
                          f"{checkpoint} est deja a la frontiere du jour PT. "
                          f"{saut} transfert(s) du jour EN COURS ignores (ils "
                          f"seront traites quand la journee PT sera close). "
                          f"C'est `chain-catchup` (07:30 UTC) qui ecrit la "
                          f"journee de la veille — cette etape lui est "
                          f"POSTERIEURE de ~19 h et n'a normalement rien a "
                          f"reprendre.", flush=True)
                else:
                    # ⭐ Le cas qui doit inquieter : rien a sauter ET rien
                    # trouve. La, le filtre n'explique pas le zero.
                    print(f"  ⚠️ ZERO INEXPLIQUE : {meta.get('pages', 0)} page(s) "
                          f"parcourue(s), 0 transfert retenu et 0 ignore. "
                          f"Ce n'est PAS le cas de figure connu (frontiere de "
                          f"jour PT) — a aller lire.", flush=True)
            rows = cc.aggregate_daily(records)
            added = cs.append_activity(sheet_id, rows)
            cs.append_items(sheet_id, cc.aggregate_items(records))
            pruned = cs.prune_activity(sheet_id) + cs.prune_items(sheet_id)

        # CONTINUITE DE L'ARCHIVE : les journees PT completes traitees ce run
        # partent en archive/ (upload Release chain-archive-daily par le workflow).
        cutoff_pt_day = cutoff.replace(tzinfo=_dt.timezone.utc) \
            .astimezone(cc.PT).strftime("%Y-%m-%d")
        arch = _archive_records(records if records_archive is None else records_archive,
                                cutoff_pt_day)
        st = _archive_stock(meta.get("stock"), cutoff_pt_day)
        if st:
            summary["stock_days"] = len(st)
            summary["stock_rows"] = sum(st.values())
            print(f"Stock chaine 2 : {sum(st.values())} mints sans metadonnee -> "
                  f"archive_stock/ (a part).", flush=True)
        if arch:
            summary["archived_days"] = len(arch)
            summary["archived_rows"] = sum(arch.values())
            print(f"Archive quotidienne : {len(arch)} journee(s), "
                  f"{sum(arch.values())} transferts -> archive/.", flush=True)

        # LISTING quotidien (groupe a part sur 📊 STATS) : nouveaux depots
        # escrow + comptes "purs" (listent sans mint/achat/vente ce jour-la).
        listing_rows = cc.aggregate_listing_daily(records)
        if listing_rows:
            summary["listing_days"] = cs.merge_listing_daily(
                sheet_id, listing_rows, replace=(mode == "backfill"))

        # _EscrowListings SUPPRIME (audit du 12/07) : cet onglet cache (59 503
        # lignes, et il grossissait chaque nuit) n'etait lu QUE par
        # veve_market.py, hors service depuis que la session VeVe est bloquee
        # et que l'onglet MarketListings n'existe plus. Il est reconstructible
        # a tout moment depuis l'archive on-chain si le Market VeVe revit.
        # Mettre CHAIN_ESCROW=true pour le realimenter.
        esc_added = 0
        if os.environ.get("CHAIN_ESCROW", "false").strip().lower() == "true":
            esc_added = cs.merge_escrow(sheet_id, cc.escrow_listings(records))

        # Registre wallets (data/wallet_registry_daily.csv) — voir wallet_scan.py.
        # Non bloquant : le suivi on-chain du Sheet ne depend pas du registre.
        try:
            from scraper import wallet_scan as ws
            summary.update(ws.update_from_records(records))
        except Exception as e:
            print(f"wallet registry warning: {e}", flush=True)

        summary.update(transfers_fetched=meta["count"], pages=meta["pages"],
                       migration_ecartee=meta.get("migration_ecartee", 0),
                       activity_rows_added=added, rows_pruned=pruned,
                       escrow_listings_added=esc_added)

        # Recompute the window stats from everything in the tab. Windows are
        # anchored on the last COMPLETE day (24h = yesterday), since today is
        # deliberately not collected yet.
        print("Reading ChainActivity to recompute the window stats...", flush=True)
        activity = cs.read_activity(sheet_id)
        stats = cc.compute_window_stats(activity, today=last_complete_day)

        for s in stats:
            if s["window"] == "24h" and s["scope"] == "all" and s["category"] == "all":
                summary["unique_accounts_24h"] = s["unique_accounts"]

        # DropRevenue abandoned: raw per-item counts stay in ChainItems (hidden)
        # for any external drop-revenue analysis.

        # Only advance the checkpoint after everything else succeeded.
        if meta.get("newest_block"):
            cs.write_meta(sheet_id, meta, totals)

    except Exception as e:
        summary["status"] = "FAILED"
        summary["note"] = str(e)[:300]
        try:
            cs.append_chain_runlog(sheet_id, summary)
        except Exception:
            pass
        raise

    summary["note"] = (summary["note"] + f" duration={time.time()-t0:.0f}s").strip()
    cs.append_chain_runlog(sheet_id, summary)
    print(f"Done: {summary}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
