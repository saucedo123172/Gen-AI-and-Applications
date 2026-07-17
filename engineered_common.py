"""
engineered_common.py
---------------------
Shared config + helpers for the ENGINEERED RAG pipeline.

ingest_engineered.py and run_engineered.py BOTH import from here. This matters:
if the embedder used to build the index ever differs from the embedder used to
query it, retrieval silently returns garbage. Keeping them in one module makes
that class of bug impossible.

What makes the ENGINEERED version different from the baseline
------------------------------------------------------------
1. Structure-aware chunking      -> tables are never sliced in half; each chunk
   (chunk_text)                     is prefixed with its section header + period
                                    so the embedding "knows" what it is.
2. Upgraded embeddings           -> bge-small-en-v1.5 (retrieval-tuned, cosine)
   (load_embedding_model)           instead of the baseline's default MiniLM.
                                    Falls back to Chroma's default if the
                                    sentence-transformers package is missing.
3. Year metadata FILTER + lag    -> the Treasury Bulletin prints a period's data
   (candidate_years)                in a LATER-dated issue, so we filter to
                                    year .. year+LAG, not an exact match.
4. Over-fetch + rerank           -> pull a wide net (OVERFETCH_K) inside the
   (rerank in run_engineered)       filter, then rerank down to TOP_K using a
                                    cross-encoder (or a month-proximity tie-break
                                    that uses the month tag) .
"""

import re

# ------------------------------- config -------------------------------------
DATA_DIR = "data"                 # treasury_bulletin_YYYY_MM.txt files
DB_DIR = "chroma_db"              # same on-disk store as baseline, new collection
COLLECTION = "engineered"

# Chunking (structure-aware): smaller windows than baseline, tables protected.
CHUNK_TOKENS = 400
OVERLAP_TOKENS = 60
MAX_TABLE_TOKENS = 1100           # keep a table whole up to this size; only split
                                  # (repeating its header row) if it's bigger.

# Embeddings: upgrade from baseline all-MiniLM-L6-v2 to a retrieval-tuned model.
EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
# bge models want this instruction on the QUERY side only (docs get no prefix).
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

# Retrieval
TOP_K = 5
OVERFETCH_K = 25                  # retrieve wide, then rerank down to TOP_K
YEAR_LAG_BUFFER = 1               # include mentioned_year .. mentioned_year+buffer
                                  # so "year-end 2022" (printed Mar-2023) is reachable

# Reranking
USE_CROSS_ENCODER = True          # set False to skip the heavy model; falls back
                                  # to month-proximity reranking automatically.
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"


# --------------------------- tokenizer (shared) -----------------------------
try:
    import tiktoken

    _enc = tiktoken.get_encoding("cl100k_base")

    def encode(text):
        return _enc.encode(text)

    def decode(tokens):
        return _enc.decode(tokens)

except Exception:  # pragma: no cover - offline fallback, matches baseline
    def encode(text):
        return text.split(" ")

    def decode(tokens):
        return " ".join(tokens)


def ntok(text: str) -> int:
    return len(encode(text))


# ------------------------- structure-aware chunking -------------------------
def _is_header(line: str) -> bool:
    return line.lstrip().startswith("#")


def _is_table_row(line: str) -> bool:
    # A markdown table row has at least two pipes ( | a | b | ).
    return line.strip().count("|") >= 2


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    return bool(s) and "-" in s and "|" in s and re.fullmatch(r"[\s:|\-]+", s) is not None


def _segment(text: str):
    """Split raw text into ordered segments, each tagged prose|table|header,
    carrying the nearest preceding section header as context."""
    lines = text.split("\n")
    segments, buf = [], []
    cur_header = ""
    i = 0

    def flush_prose():
        nonlocal buf
        if any(s.strip() for s in buf):
            segments.append({"type": "prose", "text": "\n".join(buf).strip(),
                             "header": cur_header})
        buf = []

    while i < len(lines):
        line = lines[i]

        if _is_header(line):
            flush_prose()
            cur_header = line.strip().lstrip("#").strip()
            segments.append({"type": "header", "text": line.strip(),
                             "header": cur_header})
            i += 1
            continue

        if _is_table_row(line) or _is_table_sep(line):
            flush_prose()
            tbl = []
            while i < len(lines):
                ln = lines[i]
                if _is_table_row(ln) or _is_table_sep(ln):
                    tbl.append(ln)
                    i += 1
                elif ln.strip() == "" and i + 1 < len(lines) and _is_table_row(lines[i + 1]):
                    tbl.append(ln)  # blank line inside a table; keep it
                    i += 1
                else:
                    break
            segments.append({"type": "table", "text": "\n".join(tbl).strip(),
                             "header": cur_header})
            continue

        buf.append(line)
        i += 1

    flush_prose()
    return segments


def _window_prose(text: str):
    """Token-window an oversized prose block, with overlap (baseline-style, but
    only applied to prose that is genuinely too long to fit in one chunk)."""
    toks = encode(text)
    step = CHUNK_TOKENS - OVERLAP_TOKENS
    out = []
    for start in range(0, len(toks), step):
        window = toks[start:start + CHUNK_TOKENS]
        if not window:
            break
        out.append(decode(window))
        if start + CHUNK_TOKENS >= len(toks):
            break
    return out


def _split_big_table(text: str):
    """Split a table that is too large by ROWS, repeating the header + separator
    on every piece so no piece is a headless fragment."""
    rows = [r for r in text.split("\n") if r.strip()]
    header_rows = []
    for r in rows[:2]:
        header_rows.append(r)
        if _is_table_sep(r):
            break
    body = rows[len(header_rows):]
    header_txt = "\n".join(header_rows)
    header_tok = ntok(header_txt)

    pieces, cur = [], []
    cur_tok = header_tok
    for row in body:
        rt = ntok(row)
        if cur and cur_tok + rt > MAX_TABLE_TOKENS:
            pieces.append(header_txt + "\n" + "\n".join(cur))
            cur, cur_tok = [], header_tok
        cur.append(row)
        cur_tok += rt
    if cur:
        pieces.append(header_txt + "\n" + "\n".join(cur))
    return pieces


def chunk_text(text: str):
    """Return a list of (section_header, chunk_body) tuples.

    Packing rules:
      - tables are kept whole (split by rows only if > MAX_TABLE_TOKENS)
      - oversized prose is token-windowed with overlap
      - small segments are packed together up to CHUNK_TOKENS
    """
    segs = _segment(text)
    chunks = []
    cur_parts, cur_tok, cur_header = [], 0, ""

    def emit():
        nonlocal cur_parts, cur_tok
        if cur_parts:
            chunks.append((cur_header, "\n\n".join(cur_parts).strip()))
        cur_parts, cur_tok = [], 0

    for seg in segs:
        stext, stype = seg["text"], seg["type"]
        if not stext:
            continue

        # oversized standalone segments -> emit on their own
        if stype == "table" and ntok(stext) > MAX_TABLE_TOKENS:
            emit()
            for piece in _split_big_table(stext):
                chunks.append((seg["header"], piece))
            continue
        if stype == "prose" and ntok(stext) > CHUNK_TOKENS:
            emit()
            for piece in _window_prose(stext):
                chunks.append((seg["header"], piece))
            continue

        stok = ntok(stext)
        if cur_parts and cur_tok + stok > CHUNK_TOKENS:
            emit()
        if not cur_parts:
            cur_header = seg["header"]
        cur_parts.append(stext)
        cur_tok += stok

    emit()
    # drop empty
    return [(h, b) for (h, b) in chunks if b.strip()]


def contextualize(period_label: str, header: str, body: str) -> str:
    """Prefix a chunk with its period + section so the embedding is self-describing.
    e.g.  [2024-03 | Federal Debt] <table rows...>
    This is a cheap, large win: the vector 'knows' which report + section it's from."""
    tag = period_label if not header else f"{period_label} | {header}"
    return f"[{tag}]\n{body}"


# --------------------------- metadata / query helpers -----------------------
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def mentioned_years(question: str):
    """Every 4-digit year referenced in the question, ascending."""
    return sorted({int(y) for y in _YEAR_RE.findall(question)})


def candidate_years(question: str, buffer: int = YEAR_LAG_BUFFER):
    """Years to allow through the metadata filter.

    Treasury Bulletin publishes a period's data in a later-dated issue, so we
    include the mentioned year(s) AND the next `buffer` year(s). Returns None
    when the question names no year (-> no filter, search everything)."""
    yrs = mentioned_years(question)
    if not yrs:
        return None
    out = set()
    for y in yrs:
        for d in range(0, buffer + 1):
            out.add(y + d)
    return sorted(out)


def target_period(question: str):
    """Best-guess (year, month) the question is really asking about, used for the
    month-proximity tie-break. Falls back to (max_year, 12) for 'year-end'/'CY'
    style questions when no explicit month is present."""
    yrs = mentioned_years(question)
    if not yrs:
        return None
    year = max(yrs)
    q = question.lower()
    month = None
    for name, num in _MONTHS.items():
        if name in q:
            month = num  # last month name wins (usually the 'as of' date)
    if month is None:
        month = 12  # year-end / fiscal-year questions anchor to December
    return (year, month)


def period_distance(chunk_year, chunk_month, target):
    """Absolute distance in months between a chunk's period and the target."""
    if target is None or chunk_year is None or chunk_month is None:
        return 0
    ty, tm = target
    return abs((int(chunk_year) * 12 + int(chunk_month)) - (ty * 12 + tm))


# ------------------------------ embeddings ----------------------------------
def load_embedding_model():
    """Load the bge sentence-transformer. Returns the model, or None if the
    package/model isn't available (caller then falls back to Chroma default)."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(EMBED_MODEL_NAME)
    except Exception as e:  # pragma: no cover
        print(f"WARNING: could not load {EMBED_MODEL_NAME} ({e}); "
              f"falling back to ChromaDB default embeddings.")
        return None


def embed_documents(model, texts):
    return model.encode(list(texts), normalize_embeddings=True,
                        show_progress_bar=False).tolist()


def embed_query(model, text):
    return model.encode([BGE_QUERY_INSTRUCTION + text],
                        normalize_embeddings=True,
                        show_progress_bar=False)[0].tolist()
