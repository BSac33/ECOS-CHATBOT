# corpus.py
"""
Corpus officiel du 2e cycle : import des chapitres et recherche d'extraits.

Source actuelle : référentiel de cardiologie du Collège national des enseignants de
cardiologie publié par la SFC (https://www.sfcardio.fr/formation/dfasm/), utilisé avec
l'accord du collège et d'UNESS. Les textes restent la propriété de leurs auteurs et
éditeur : ils sont stockés en base pour l'assistant de rédaction, jamais dans le dépôt,
et chaque extrait renvoie à sa source (URL + section).

- parse_sfc_chapter(html, url) : un chapitre -> item R2C, situations de départ,
  objectifs hiérarchisés (rangs A/B), extraits par section avec leur rang
- store_chapter(session, ...)   : enregistre (remplace) un chapitre, met à jour les
  items EDN, les situations de départ et leurs liens
- search_corpus(session, ...)   : BM25 sur les extraits, filtrable par item et type

La recherche est lexicale (BM25 en Python) : quelques milliers d'extraits, des requêtes
rares (rédaction d'un cas), pas besoin d'index vectoriel pour commencer.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import delete
from sqlmodel import Session, select

from models import CorpusChunk, CorpusSource, EDNItem, ItemSituationLink, StartingSituation

# ==================== SOURCES ====================

SFC_SOURCE = CorpusSource(
    id="sfc-cnec-cardio",
    title="Référentiel de cardiologie du Collège national des enseignants de cardiologie (DFASM)",
    publisher="Collège national des enseignants de cardiologie (CNEC) / Société française de cardiologie",
    license_note=("Utilisation accordée par le collège de cardiologie et UNESS pour la plateforme "
                  "d'entraînement ECOS. Textes © leurs auteurs et éditeur : ne pas les redistribuer "
                  "hors de la plateforme, toujours citer la source."),
    homepage="https://www.sfcardio.fr/formation/dfasm/",
)

CHAPTER_LINK_RE = re.compile(r'href="(?:https?://(?:www\.)?sfcardio\.fr)?(/publication/chapitre-[^"#?]+)')


def chapter_urls(index_html: str, base: str = "https://www.sfcardio.fr") -> List[str]:
    """Liens des chapitres sur la page d'index du DFASM, dans l'ordre, sans doublon."""
    seen, out = set(), []
    for path in CHAPTER_LINK_RE.findall(index_html):
        url = base + path
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


# ==================== ANALYSE D'UN CHAPITRE ====================

MAX_CHUNK = 1200        # caractères par extrait

# « CHAPITRE 5 : Item 339 – Titre », « Chapitre 08 – Item 233 : Titre », « Chapitre 09 – Item : 152 Titre »
H1_RE = re.compile(r"chapitre\s+(\d+)\s*[:–—-]\s*items?\s*:?\s*(\d+)\s*[:–—-]?\s*(.+)", re.I)
RANK_RE = re.compile(r"^\s*rang\s+([abc])\b", re.I)
SITUATION_RE = re.compile(r"^(\d{1,3})\s+(.+?)\s*\.?$")
CAPTION_RE = re.compile(r"^(tableau|figure|encadré)\s", re.I)

# Titre de section (normalisé) -> type d'extrait ; None = section ignorée
SPECIAL_SECTIONS = {
    "sommaire": None,
    "reflexes transversalite": None,
    "situations de depart": "situations",
    "hierarchisation des connaissances": "objectifs",
    "vignette clinique": "vignette",
    "points cles": "points_cles",
    "notions indispensables et inacceptables": "notions",
}


@dataclass
class Objective:
    rank: Optional[str]
    rubric: str
    text: str


@dataclass
class Chunk:
    section: str
    rank: Optional[str]
    kind: str
    text: str


@dataclass
class ParsedChapter:
    url: str
    chapter_number: Optional[int]
    item_number: Optional[int]
    item_title: str
    situations: List[tuple] = field(default_factory=list)     # [(161, "Douleur thoracique")]
    objectives: List[Objective] = field(default_factory=list)
    chunks: List[Chunk] = field(default_factory=list)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _clean(text: str) -> str:
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _rank_of(el) -> Optional[str]:
    img = el.find("img", alt=RANK_RE) if hasattr(el, "find") else None
    if img is None and getattr(el, "name", None) == "img" and RANK_RE.match(el.get("alt") or ""):
        img = el
    return RANK_RE.match(img["alt"]).group(1).upper() if img is not None else None


def _inline_text(el) -> str:
    """Texte d'un bloc : <br> = retour à la ligne, éléments en ligne collés."""
    from bs4 import NavigableString, Tag

    parts: List[str] = []

    def walk(node):
        for child in node.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif isinstance(child, Tag):
                if child.name == "br":
                    parts.append("\n")
                elif child.name in ("ul", "ol"):
                    parts.append("\n" + _list_text(child, depth=1))
                elif child.name != "img":
                    walk(child)
    walk(el)
    return _clean("".join(parts))


def _list_text(el, depth: int = 0) -> str:
    items = []
    for li in el.find_all("li", recursive=False):
        items.append("  " * depth + "- " + _inline_text(li).replace("\n", "\n" + "  " * (depth + 1)))
    return "\n".join(items)


def _table_rows(table) -> List[List[str]]:
    return [[_inline_text(c).replace("\n", " ") for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]


def _block_text(el) -> str:
    if el.name in ("ul", "ol"):
        return _list_text(el)
    table = el if el.name == "table" else el.find("table")
    if table is not None:
        return "\n".join(" | ".join(c for c in row if c) for row in _table_rows(table) if any(row))
    return _inline_text(el)


def _content_root(soup):
    main = soup.find("main") or soup
    marker = main.find(lambda t: t.name == "h2" and _norm(t.get_text(" ", strip=True)).startswith("situations de depart"))
    if marker is not None:
        return marker.parent
    h2s = main.find_all("h2")
    if not h2s:
        return main
    parents = Counter(id(h.parent) for h in h2s)
    best = parents.most_common(1)[0][0]
    return next(h.parent for h in h2s if id(h.parent) == best)


def parse_sfc_chapter(html: str, url: str) -> ParsedChapter:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    title = _inline_text(h1).replace("\n", " ") if h1 else ""
    m = H1_RE.search(title)
    chapter = ParsedChapter(
        url=url,
        chapter_number=int(m.group(1)) if m else None,
        item_number=int(m.group(2)) if m else None,
        item_title=m.group(3).strip() if m else title,
    )

    path = {2: "", 3: "", 4: ""}
    kind: Optional[str] = None
    rank: Optional[str] = None
    caption = ""
    buffer: List[str] = []
    buffer_key = None

    def flush():
        nonlocal buffer, buffer_key
        if buffer and buffer_key:
            section, brank, bkind = buffer_key
            chapter.chunks.append(Chunk(section=section, rank=brank, kind=bkind, text="\n".join(buffer)))
        buffer, buffer_key = [], None

    def add(text: str):
        nonlocal buffer, buffer_key
        section = " > ".join(t for t in (path[2], path[3], path[4]) if t)
        key = (section, rank, kind)
        if key != buffer_key or sum(len(b) for b in buffer) + len(text) > MAX_CHUNK:
            flush()
            buffer_key = key
        # Bloc trop long : découpé par lignes
        while len(text) > MAX_CHUNK:
            cut = text.rfind("\n", 0, MAX_CHUNK)
            cut = cut if cut > 0 else MAX_CHUNK
            buffer.append(text[:cut].strip())
            flush()
            buffer_key = key
            text = text[cut:].strip()
        if text:
            buffer.append(text)

    for el in _content_root(soup).children:
        name = getattr(el, "name", None)
        if not name:
            continue
        if name in ("h1",):
            continue
        if name in ("h2", "h3", "h4"):
            heading = _inline_text(el).replace("\n", " ").rstrip(" .")
            level = int(name[1])
            if level >= 3 and CAPTION_RE.match(heading):
                caption = heading            # légende du tableau qui suit
                rank = _rank_of(el) or rank
                continue
            flush()
            if level == 2:
                special = _norm(heading)
                kind = SPECIAL_SECTIONS[special] if special in SPECIAL_SECTIONS else "cours"
                rank = None
                path = {2: heading, 3: "", 4: ""}
            elif level == 3:
                path[3], path[4] = heading, ""
            else:
                path[4] = heading
            rank = _rank_of(el) or rank
            continue
        if kind is None:
            continue

        # Cours qui commence sans titre sous les situations ou les objectifs (ex. item 330)
        if (kind == "situations" and el.find("li") is None and name not in ("ul", "ol")) or \
                (kind == "objectifs" and name != "table" and el.find("table") is None):
            kind, path = "cours", {2: "Introduction", 3: "", 4: ""}

        if kind == "situations":
            for li in el.find_all("li"):
                sm = SITUATION_RE.match(_inline_text(li).replace("\n", " "))
                if sm:
                    chapter.situations.append((int(sm.group(1)), sm.group(2).strip()))
            continue
        if kind == "objectifs":
            table = el if name == "table" else el.find("table")
            if table is None:
                continue
            for tr in table.find_all("tr"):
                cells = tr.find_all(["td", "th"])
                if len(cells) < 3 or tr.find("th") is not None:
                    continue
                rubric, text = _inline_text(cells[1]), _inline_text(cells[2])
                if _norm(rubric) == "rubrique" or not text:
                    continue
                chapter.objectives.append(Objective(rank=_rank_of(cells[0]), rubric=rubric, text=text))
            continue

        rank = _rank_of(el) or rank
        text = _block_text(el)
        if caption and (name == "table" or el.find("table") is not None):
            text = f"{caption}\n{text}"
            caption = ""
        if text:
            add(text)
    flush()
    return chapter


# ==================== STOCKAGE ====================

def store_chapter(session: Session, chapter: ParsedChapter, source: CorpusSource = SFC_SOURCE) -> int:
    """Enregistre un chapitre (remplace ses extraits). Retourne le nombre d'extraits."""
    existing = session.get(CorpusSource, source.id)
    if existing is None:
        session.add(CorpusSource(**source.model_dump(exclude={"retrieved_at"}), retrieved_at=datetime.now()))
    else:
        for key, value in source.model_dump(exclude={"id", "retrieved_at"}).items():
            setattr(existing, key, value)
        existing.retrieved_at = datetime.now()
        session.add(existing)
    session.flush()

    session.execute(delete(CorpusChunk).where(CorpusChunk.source_id == source.id, CorpusChunk.url == chapter.url))
    rows = [CorpusChunk(source_id=source.id, url=chapter.url, item_number=chapter.item_number,
                        chapter_title=chapter.item_title, section=o.rubric, rank=o.rank,
                        kind="objectif", position=i, text=o.text)
            for i, o in enumerate(chapter.objectives)]
    offset = len(rows)
    rows += [CorpusChunk(source_id=source.id, url=chapter.url, item_number=chapter.item_number,
                         chapter_title=chapter.item_title, section=c.section, rank=c.rank,
                         kind=c.kind, position=offset + i, text=c.text)
             for i, c in enumerate(chapter.chunks)]
    session.add_all(rows)

    if chapter.item_number is not None:
        item = session.exec(select(EDNItem).where(EDNItem.number == chapter.item_number)).first()
        clash = session.exec(select(EDNItem).where(EDNItem.title == chapter.item_title,
                                                   EDNItem.number != chapter.item_number)).first()
        if item is None and clash is None:
            session.add(EDNItem(number=chapter.item_number, title=chapter.item_title))
        elif item is not None and clash is None and item.title != chapter.item_title:
            item.title = chapter.item_title
            session.add(item)
        for number, title in dict(chapter.situations).items():
            situation = session.get(StartingSituation, number)
            if situation is None:
                session.add(StartingSituation(number=number, title=title))
            elif situation.title != title:
                situation.title = title
                session.add(situation)
            if session.get(ItemSituationLink, (chapter.item_number, number)) is None:
                session.add(ItemSituationLink(item_number=chapter.item_number, situation_number=number))
    session.flush()
    return len(rows)


# ==================== RECHERCHE ====================

STOPWORDS = set("""
a au aux avec ce ces cette d dans de des du elle en et est etre il ils l la le les leur lui
mais me meme ne ni nos notre on ou par pas pour qu que qui sa se ses si son sont sur ta te
tes ton tu un une vos votre y plus moins tres sans sous chez entre lors dont cas
""".split())


def tokenize(text: str) -> List[str]:
    tokens = []
    for tok in re.findall(r"[a-z0-9]+", _norm(text)):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        if len(tok) > 4 and tok[-1] in "sx":     # pluriels
            tok = tok[:-1]
        tokens.append(tok)
    return tokens


@dataclass
class CorpusHit:
    chunk_id: int
    item_number: Optional[int]
    chapter_title: str
    section: str
    rank: Optional[str]
    kind: str
    text: str
    url: str
    source_id: str
    score: float

    @property
    def label(self) -> str:
        item = f"Item {self.item_number} – " if self.item_number else ""
        return f"{item}{self.chapter_title} › {self.section}" if self.section else f"{item}{self.chapter_title}"


def bm25(query: Sequence[str], docs: List[List[str]], k1: float = 1.4, b: float = 0.75) -> List[float]:
    if not docs:
        return []
    n = len(docs)
    avg = sum(len(d) for d in docs) / n or 1.0
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for t in set(query):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        scores.append(s)
    return scores


def search_corpus(session: Session, query: str, items: Optional[Iterable[int]] = None,
                  kinds: Optional[Iterable[str]] = None, limit: int = 6) -> List[CorpusHit]:
    stmt = select(CorpusChunk)
    items = [i for i in (items or []) if i]
    if items:
        stmt = stmt.where(CorpusChunk.item_number.in_(items))
    if kinds:
        stmt = stmt.where(CorpusChunk.kind.in_(list(kinds)))
    chunks = session.exec(stmt).all()
    q = tokenize(query)
    if not q or not chunks:
        return []
    # Le titre de section compte dans l'indexation (ex. « Interrogatoire »)
    docs = [tokenize(f"{c.section} {c.text}") for c in chunks]
    scored = sorted(zip(bm25(q, docs), chunks), key=lambda x: (-x[0], x[1].position))
    return [CorpusHit(chunk_id=c.id, item_number=c.item_number, chapter_title=c.chapter_title,
                      section=c.section, rank=c.rank, kind=c.kind, text=c.text, url=c.url,
                      source_id=c.source_id, score=round(s, 3))
            for s, c in scored[:limit] if s > 0]


def objectives(session: Session, items: Iterable[int]) -> List[CorpusChunk]:
    """Objectifs hiérarchisés des items (rang A d'abord)."""
    items = [i for i in items if i]
    if not items:
        return []
    stmt = select(CorpusChunk).where(CorpusChunk.kind == "objectif", CorpusChunk.item_number.in_(items))
    return sorted(session.exec(stmt).all(), key=lambda c: (c.rank or "Z", c.item_number or 0, c.position))
