"""
ingest_engineered.py
--------------------
ENGINEERED ingestion. Same files as the baseline, three deliberate upgrades:

  1. Structure-aware chunking  (engineered_common.chunk_text)
       - tables are kept whole (a sliced table is unreadable no matter how good
         the model is); only tables > MAX_TABLE_TOKENS are split, by rows, with
         the header row repeated on each piece.
       - each chunk is prefixed with its period + section header
         (e.g. "[2024-03 | Federal Debt] ...") so the embedding is self-describing.

  2. Upgraded embeddings       (bge-small-en-v1.5, cosine, L2-normalized)
       - replaces the baseline's default all-MiniLM-L6-v2.
       - graceful fallback to Chroma's default embeddings if
         sentence-transformers isn't installed.

  3. Year / Month metadata     (unchanged tags, but now the QUERY side uses them)
       - every chunk still carries {source, year, month, chunk_index};
         run_engineered.py filters on `year` and tie-breaks on `month`.

Run:  python ingest_engineered.py
"""

import glob
import os
import re

import chromadb

import engineered_common as ec


def parse_year_month(filename: str):
    """treasury_bulletin_2024_03.txt -> (2024, 3)."""
    m = re.search(r"(\d{4})_(\d{2})", filename)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def period_label(year, month):
    return f"{year}-{month:02d}" if year and month else "unknown-period"


def main():
    client = chromadb.PersistentClient(path=ec.DB_DIR)

    # start fresh each run so re-ingesting never duplicates chunks
    try:
        client.delete_collection(ec.COLLECTION)
    except Exception:
        pass

    model = ec.load_embedding_model()
    if model is not None:
        # cosine space + we supply our own normalized bge vectors
        collection = client.create_collection(
            ec.COLLECTION,
            metadata={"hnsw:space": "cosine", "embedder": ec.EMBED_MODEL_NAME},
        )
        print(f"Embeddings: {ec.EMBED_MODEL_NAME} (cosine)")
    else:
        # fallback: let Chroma embed with its default model
        collection = client.create_collection(
            ec.COLLECTION, metadata={"embedder": "chroma-default"}
        )
        print("Embeddings: ChromaDB default (fallback)")

    files = sorted(glob.glob(os.path.join(ec.DATA_DIR, "*.txt")))
    if not files:
        raise SystemExit(f"No .txt files found in {ec.DATA_DIR}/ -- check the path.")

    total = 0
    for path in files:
        fname = os.path.basename(path)
        year, month = parse_year_month(fname)
        plabel = period_label(year, month)

        with open(path, encoding="utf-8") as f:
            text = f.read()

        pairs = ec.chunk_text(text)  # list of (header, body)
        docs, ids, metas = [], [], []
        for i, (header, body) in enumerate(pairs):
            docs.append(ec.contextualize(plabel, header, body))
            ids.append(f"{fname}::chunk{i}")
            metas.append(
                {
                    "source": fname,
                    "year": year,
                    "month": month,
                    "section": header[:120],
                    "chunk_index": i,
                }
            )

        BATCH = 100
        for start in range(0, len(docs), BATCH):
            batch_docs = docs[start:start + BATCH]
            kwargs = dict(
                documents=batch_docs,
                ids=ids[start:start + BATCH],
                metadatas=metas[start:start + BATCH],
            )
            if model is not None:
                kwargs["embeddings"] = ec.embed_documents(model, batch_docs)
            collection.add(**kwargs)

        total += len(docs)
        print(f"  {fname}: {len(docs)} chunks")

    print(f"\nDone. {total} chunks in collection '{ec.COLLECTION}' at ./{ec.DB_DIR}")
    print("Next: python run_engineered.py")


if __name__ == "__main__":
    main()
