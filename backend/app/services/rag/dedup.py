"""Filter RAG hits already supplied as chapter context (no store writes)."""
from app.db.vector_store import VectorChunkRecord


def filter_history_hits(
    hits: list[tuple[VectorChunkRecord, float]], *,
    excluded_chapter_ids: set[int], history_texts: list[str],
) -> list[tuple[VectorChunkRecord, float]]:
    # Any common continuous 20-character span meets the overlap threshold.
    known_spans: set[str] = set()
    for history in history_texts:
        text = "".join(history.split())
        known_spans.update(text[i:i + 20] for i in range(len(text) - 19))
    kept = []
    for record, score in hits:
        if record.chapter_id in excluded_chapter_ids:
            continue
        text = "".join(record.text.split())
        if not text or any(text[i:i + 20] in known_spans for i in range(len(text) - 19)):
            continue
        kept.append((record, score))
    return kept
