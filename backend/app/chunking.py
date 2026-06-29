"""Paragraph-aware chunking.

Why not split every N characters: cutting mid-sentence destroys meaning,
which directly hurts retrieval quality. We pack whole paragraphs up to a
size budget, then keep a small overlap so context isn't lost at boundaries.

Interview point: chunking strategy is one of the highest-leverage tuning
knobs in RAG. Bad chunking = bad retrieval, no matter how good your model.
The right next upgrade for code/markdown is a structure-aware splitter
(split at function boundaries, headings etc.) -- noted as a future improvement.
"""


def chunk_text(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            # start next chunk with tail of previous one (the overlap)
            tail = current[-overlap:] if overlap and current else ""
            current = f"{tail}\n\n{para}".strip() if tail else para

            # a single oversized paragraph still needs to be emitted
            while len(current) > size:
                chunks.append(current[:size])
                current = current[size - overlap:]

    if current:
        chunks.append(current)
    return chunks