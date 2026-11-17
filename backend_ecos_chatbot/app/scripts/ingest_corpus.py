#!/usr/bin/env python3
"""
Import du référentiel de cardiologie (CNEC / SFC, DFASM) dans le corpus officiel.

Utilisation autorisée par le collège de cardiologie et UNESS (voir docs/CASE_AUTHORING.md).
Les textes vont en base (tables corpus_*), jamais dans le dépôt.

    cd backend_ecos_chatbot/app
    python scripts/ingest_corpus.py                         # télécharge les 22 chapitres
    python scripts/ingest_corpus.py --cache-dir /data/sfc   # + garde le HTML brut
    python scripts/ingest_corpus.py --from-dir /data/sfc    # réimporte sans réseau
    python scripts/ingest_corpus.py --limit 2 --dry-run     # vérifie l'analyse, n'écrit rien

Idempotent : un chapitre réimporté remplace ses extraits. Les items EDN, situations de
départ et liens item ↔ situation sont mis à jour au passage.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

USER_AGENT = "ECOS-Chatbot corpus import (usage pedagogique autorise)"
URL_META_RE = re.compile(r'<meta property="og:url" content="([^"]+)"')


def fetch(client, url: str) -> str:
    for attempt in range(3):
        try:
            response = client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # réseau capricieux : on réessaie poliment
            if attempt == 2:
                raise
            print(f"   ↻ {url} : {exc}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("inaccessible")


def pages_from_web(index_url: str, delay: float, limit: int | None, cache_dir: Path | None):
    import httpx

    from corpus import chapter_urls

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as client:
        urls = chapter_urls(fetch(client, index_url))
        if not urls:
            raise SystemExit(f"Aucun chapitre trouvé sur {index_url}")
        print(f"📚 {len(urls)} chapitres trouvés")
        for i, url in enumerate(urls[:limit]):
            if i:
                time.sleep(delay)
            html = fetch(client, url)
            if cache_dir:
                cache_dir.mkdir(parents=True, exist_ok=True)
                (cache_dir / (url.rstrip("/").rsplit("/", 1)[-1] + ".html")).write_text(html, encoding="utf-8")
            yield url, html


def pages_from_dir(directory: Path, limit: int | None):
    count = 0
    for path in sorted(directory.glob("*.html")):
        html = path.read_text(encoding="utf-8")
        m = URL_META_RE.search(html)
        if not m or "/publication/chapitre-" not in m.group(1):
            continue                      # page d'index ou autre page du site
        if limit is not None and count >= limit:
            return
        count += 1
        yield m.group(1), html


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--index", default="https://www.sfcardio.fr/formation/dfasm/")
    parser.add_argument("--from-dir", type=Path, help="chapitres HTML déjà téléchargés")
    parser.add_argument("--cache-dir", type=Path, help="garder une copie du HTML téléchargé")
    parser.add_argument("--delay", type=float, default=2.0, help="pause entre deux pages (s)")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true", help="analyser sans écrire en base")
    args = parser.parse_args()

    from corpus import parse_sfc_chapter, store_chapter

    pages = (pages_from_dir(args.from_dir, args.limit) if args.from_dir
             else pages_from_web(args.index, args.delay, args.limit, args.cache_dir))

    session = None
    if not args.dry_run:
        from sqlmodel import Session, create_engine
        session = Session(create_engine(os.environ["DATABASE_URL"]))

    total = 0
    try:
        for url, html in pages:
            chapter = parse_sfc_chapter(html, url)
            kinds = Counter(c.kind for c in chapter.chunks)
            print(f" - Item {chapter.item_number} – {chapter.item_title} : {len(chapter.objectives)} objectifs, "
                  f"{len(chapter.situations)} situations, {len(chapter.chunks)} extraits {dict(kinds)}")
            if chapter.item_number is None or not chapter.chunks:
                print(f"   ⚠️  page ignorée (structure inattendue) : {url}")
                continue
            if session is not None:
                total += store_chapter(session, chapter)
                session.commit()
    finally:
        if session is not None:
            session.close()
    if session is not None:
        print(f"✅ {total} extraits enregistrés")


if __name__ == "__main__":
    main()
