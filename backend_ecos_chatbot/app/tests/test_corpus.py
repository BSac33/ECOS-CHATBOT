"""Corpus officiel : analyse d'un chapitre (fictif, même mise en page que la SFC), stockage, recherche."""
from pathlib import Path

import pytest

from corpus import chapter_urls, parse_sfc_chapter, search_corpus, store_chapter, objectives, tokenize

FIXTURE = Path(__file__).parent / "fixtures" / "sfc_chapter_fictif.html"
URL = "https://www.sfcardio.fr/publication/chapitre-99-item-999-maladie-fictive/"


@pytest.fixture
def chapter():
    return parse_sfc_chapter(FIXTURE.read_text(encoding="utf-8"), URL)


def test_parse_header_situations_objectives(chapter):
    assert (chapter.chapter_number, chapter.item_number) == (99, 999)
    assert chapter.item_title == "Maladie fictive de Test"
    assert chapter.situations == [(161, "Douleur thoracique"), (162, "Dyspnée")]
    assert [(o.rank, o.rubric) for o in chapter.objectives] == [
        ("A", "Définition"), ("B", "Épidémiologie"), ("A", "Diagnostic positif")]


def test_title_variants():
    for title, expected in [("CHAPITRE 5 : Item 339 – Syndromes coronariens aigus", (5, 339, "Syndromes coronariens aigus")),
                            ("Chapitre 08 – Item 233 : Valvulopathies", (8, 233, "Valvulopathies")),
                            ("Chapitre 09 – Item : 152 Endocardite infectieuse", (9, 152, "Endocardite infectieuse"))]:
        ch = parse_sfc_chapter(f"<main><h1>{title}</h1></main>", URL)
        assert (ch.chapter_number, ch.item_number, ch.item_title) == expected


def test_chunks_sections_ranks_and_kinds(chapter):
    chunks = chapter.chunks
    kinds = [c.kind for c in chunks]
    assert kinds[0] == "vignette" and "points_cles" in kinds and "notions" in kinds
    text = "\n".join(c.text for c in chunks)
    # Sommaire, réflexes de transversalité et contenu hors cours ignorés
    assert "II. Diagnostic" not in text and "Item 998" not in text and "promotionnel" not in text

    definition = next(c for c in chunks if c.section == "I. Définition")
    assert definition.rank == "A"
    assert "gêne imaginaire et une fatigue" in definition.text          # éléments en ligne recollés
    assert "Elle n’existe" in definition.text.split("\n")[1]            # <br> = retour à la ligne
    assert "garde le rang" in definition.text                            # rang conservé sans badge

    interro = [c for c in chunks if c.section == "II. Diagnostic > A. Interrogatoire"]
    assert interro and all(c.rank == "B" for c in interro)
    joined = "\n".join(c.text for c in interro)
    assert "- gêne au réveil" in joined and "  - surtout après" in joined   # listes imbriquées
    assert "Tableau 99.1. Score fictif\nScore | Sens\n1 | gêne légère" in joined  # légende + tableau

    inacceptable = next(c for c in chunks if c.kind == "notions")
    assert inacceptable.section.endswith("Notions inacceptables")


def test_chapter_urls_from_index():
    html = ('<a href="/publication/chapitre-01-item-221-a/">1</a><a href="/publication/chapitre-01-item-221-a/">bis</a>'
            '<a href="https://www.sfcardio.fr/publication/chapitre-02-item-222-b/#top">2</a><a href="/autre/">x</a>')
    assert chapter_urls(html) == ["https://www.sfcardio.fr/publication/chapitre-01-item-221-a/",
                                  "https://www.sfcardio.fr/publication/chapitre-02-item-222-b/"]


def test_store_is_idempotent_and_updates_references(session, chapter):
    from sqlmodel import func, select

    from models import CorpusChunk, EDNItem, ItemSituationLink, StartingSituation

    session.add(EDNItem(number=999, title="Ancien titre"))
    session.commit()
    n = store_chapter(session, chapter)
    session.commit()
    assert n == len(chapter.objectives) + len(chapter.chunks)
    assert store_chapter(session, chapter) == n
    session.commit()
    assert session.exec(select(func.count()).select_from(CorpusChunk)).one() == n
    assert session.exec(select(EDNItem).where(EDNItem.number == 999)).one().title == "Maladie fictive de Test"
    assert {s.number for s in session.exec(select(StartingSituation)).all()} == {161, 162}
    assert len(session.exec(select(ItemSituationLink)).all()) == 2


def test_search_and_objectives(session, chapter):
    store_chapter(session, chapter)
    session.commit()
    hits = search_corpus(session, "Horaire de la gêne et tabagisme ?", items=[999])
    assert hits and "tabagisme" in hits[0].text
    assert hits[0].label.startswith("Item 999 – Maladie fictive de Test ›")
    assert search_corpus(session, "tabagisme", items=[1]) == []
    assert all(h.kind == "objectif" for h in search_corpus(session, "interrogatoire", kinds=["objectif"]))
    assert [o.rank for o in objectives(session, [999])] == ["A", "A", "B"]


def test_tokenize_folds_accents_plurals_and_stopwords():
    assert tokenize("Les Antécédents des patients") == ["antecedent", "patient"]
