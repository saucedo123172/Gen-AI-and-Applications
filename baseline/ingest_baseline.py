"""
ingest_baseline.py
------------------
BASELINE ingestion: deliberately naive.

- Fixed-size chunking: 512 tokens, 50-token overlap
- No respect for sections or tables (tables WILL get sliced in half -- that's
  the point of a baseline)
- No year/month metadata filtering (we store the source filename only for
  logging/metric purposes, but the baseline query never filters on it)
- Embeddings: ChromaDB's default (all-MiniLM-L6-v2 via ONNX)

Run:  python ingest_baseline.py
"""

import glob
import os
import re

import chromadb
import tiktoken

# ----------------------------- config ---------------------------------------
DATA_DIR = "data"            # folder containing treasury_bulletin_YYYY_MM.txt
DB_DIR = "chroma_db"         # where ChromaDB persists to disk
COLLECTION = "baseline"
CHUNK_TOKENS = 512
OVERLAP_TOKENS = 50
# -----------------------------------------------------------------------------

# tiktoken downloads its tokenizer file on first use; fall back to a
# whitespace tokenizer (~1 token per word) if that download is blocked.
try:
    _enc = tiktoken.get_encoding("cl100k_base")

    def _encode(text):
        return _enc.encode(text)

    def _decode(tokens):
        return _enc.decode(tokens)

except Exception:
    print("WARNING: tiktoken unavailable, falling back to word-based chunking.")

    def _encode(text):
        return text.split(" ")

    def _decode(tokens):
        return " ".join(tokens)


def chunk_text(text: str, size: int = CHUNK_TOKENS, overlap: int = OVERLAP_TOKENS):
    """Naive fixed-size token chunking with overlap. Ignores structure."""
    tokens = _encode(text)
    chunks = []
    step = size - overlap
    for i in range(0, len(tokens), step):
        window = tokens[i : i + size]
        if not window:
            break
        chunks.append(_decode(window))
        if i + size >= len(tokens):
            break
    return chunks


def parse_year_month(filename: str):
    """treasury_bulletin_2024_03.txt -> (2024, 3).

    Stored on every chunk for logging and metric computation.
    The BASELINE never uses it to filter -- that's the Engineered version's job.
    """
    m = re.search(r"(\d{4})_(\d{2})", filename)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def main():
    client = chromadb.PersistentClient(path=DB_DIR)

    # start fresh each run so re-ingesting doesn't duplicate chunks
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION)

    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.txt")))
    if not files:
        raise SystemExit(f"No .txt files found in {DATA_DIR}/ -- check the path.")

    total = 0
    for path in files:
        fname = os.path.basename(path)
        year, month = parse_year_month(fname)
        with open(path, encoding="utf-8") as f:
            text = f.read()

        chunks = chunk_text(text)
        ids = [f"{fname}::chunk{i}" for i in range(len(chunks))]
        metas = [
            {"source": fname, "year": year, "month": month, "chunk_index": i}
            for i in range(len(chunks))
        ]

        # add in batches so embedding progress is visible and memory stays low
        BATCH = 100
        for start in range(0, len(chunks), BATCH):
            collection.add(
                documents=chunks[start : start + BATCH],
                ids=ids[start : start + BATCH],
                metadatas=metas[start : start + BATCH],
            )
        total += len(chunks)
        print(f"  {fname}: {len(chunks)} chunks")

    print(f"\nDone. {total} chunks in collection '{COLLECTION}' at ./{DB_DIR}")


if __name__ == "__main__":
    main()
