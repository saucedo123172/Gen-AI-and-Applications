"""
run_engineered.py
-----------------
Runs every question through the ENGINEERED system and logs results in the SAME
format as run_baseline.py, so compute_metrics.py works unchanged:

    python compute_metrics.py results/engineered_results.json

Engineered retrieval pipeline (per question):
  1. candidate_years(question)  -> year filter with a publication-lag buffer
  2. ChromaDB query WITH  where={"year": {"$in": years}}, over-fetching OVERFETCH_K
  3. rerank the over-fetched set down to TOP_K:
        - cross-encoder (bge-reranker-base) if available, else
        - month-proximity tie-break using the `month` metadata tag
  4. Claude answers from the reranked top-K; a FINAL: line is parsed out so the
     graded value is clean (helps the computed-answer questions).

Requires:
  - chroma_db/ built by ingest_engineered.py
  - questions_filtered.csv
  - ANTHROPIC_API_KEY in the environment:   export ANTHROPIC_API_KEY="sk-ant-..."

Run:  python run_engineered.py
"""

import json
import os

import chromadb
import pandas as pd
from anthropic import Anthropic

import engineered_common as ec

# ----------------------------- config ---------------------------------------
QUESTIONS_CSV = "questions_filtered.csv"
QUESTION_COL = "question"          # confirmed against questions_filtered.csv
ANSWER_COL = "answer"              # confirmed against questions_filtered.csv

MODEL = "claude-sonnet-4-6"        # same LLM as baseline: isolates the gains to
                                   # retrieval + prompt, not a bigger model.
OUT_PATH = os.path.join("results", "engineered_results.json")
# -----------------------------------------------------------------------------

PROMPT_TEMPLATE = """You are answering a factual question using ONLY the context below.
The context is drawn from U.S. Treasury Bulletin tables. You may do arithmetic
(e.g. quarter-over-quarter change) using numbers that appear in the context, but
never invent a figure that is not present.

Think briefly, then finish with a single line in exactly this form:
FINAL: <the answer only -- a number, date, or short phrase; no explanation>
If the needed figures are not in the context, finish with: FINAL: Not found

Context:
{context}

Question: {question}"""


def load_reranker():
    if not ec.USE_CROSS_ENCODER:
        return None
    try:
        from sentence_transformers import CrossEncoder
        return CrossEncoder(ec.RERANK_MODEL_NAME)
    except Exception as e:
        print(f"WARNING: reranker unavailable ({e}); using month-proximity rerank.")
        return None


def rerank(question, candidates, reranker):
    """candidates: list of dicts with keys text, source, year, month, distance.
    Returns the list reordered best-first."""
    target = ec.target_period(question)

    if reranker is not None:
        pairs = [(question, c["text"]) for c in candidates]
        scores = reranker.predict(pairs)
        for c, s in zip(candidates, scores):
            # cross-encoder score (higher=better); nudge by period closeness so
            # the month tag still breaks ties between near-identical chunks.
            prox = ec.period_distance(c["year"], c["month"], target)
            c["_score"] = float(s) - 0.01 * prox
        return sorted(candidates, key=lambda c: c["_score"], reverse=True)

    # fallback: order by embedding distance, tie-broken by month proximity.
    for c in candidates:
        prox = ec.period_distance(c["year"], c["month"], target)
        c["_score"] = c["distance"] + 0.05 * prox
    return sorted(candidates, key=lambda c: c["_score"])


def extract_final(text: str) -> str:
    """Pull the value after the last 'FINAL:' line; fall back to full text."""
    marker = "FINAL:"
    idx = text.rfind(marker)
    if idx != -1:
        return text[idx + len(marker):].strip().splitlines()[0].strip()
    return text.strip()


def main():
    df = pd.read_csv(QUESTIONS_CSV)
    for col in (QUESTION_COL, ANSWER_COL):
        if col not in df.columns:
            raise SystemExit(
                f"Column '{col}' not in {QUESTIONS_CSV}. "
                f"Available columns: {list(df.columns)}"
            )

    client = chromadb.PersistentClient(path=ec.DB_DIR)
    collection = client.get_collection(ec.COLLECTION)
    used_embedder = (collection.metadata or {}).get("embedder", "")
    model = ec.load_embedding_model() if used_embedder == ec.EMBED_MODEL_NAME else None

    reranker = load_reranker()
    llm = Anthropic()  # reads ANTHROPIC_API_KEY from environment

    results = []
    for i, row in df.iterrows():
        question = str(row[QUESTION_COL])
        expected = str(row[ANSWER_COL])
        gold_sources = [
            f.strip()
            for f in str(row.get("source_files", "")).splitlines()
            if f.strip()
        ]

        # ---- 1) metadata filter (the core engineered retrieval change) ----
        years = ec.candidate_years(question)
        where = {"year": {"$in": years}} if years else None

        # ---- 2) retrieve wide (over-fetch) inside the filter ----
        query_kwargs = dict(n_results=ec.OVERFETCH_K)
        if where:
            query_kwargs["where"] = where
        if model is not None:
            query_kwargs["query_embeddings"] = [ec.embed_query(model, question)]
        else:
            query_kwargs["query_texts"] = [question]

        r = collection.query(**query_kwargs)
        cand = [
            {
                "text": doc,
                "source": m["source"],
                "year": m["year"],
                "month": m["month"],
                "chunk_index": m.get("chunk_index"),
                "distance": dist,
            }
            for doc, m, dist in zip(
                r["documents"][0], r["metadatas"][0], r["distances"][0]
            )
        ]

        # ---- 3) rerank down to TOP_K ----
        ranked = rerank(question, cand, reranker)[: ec.TOP_K]
        context = "\n\n---\n\n".join(c["text"] for c in ranked)

        # ---- 4) generate, then parse the clean FINAL value ----
        msg = llm.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT_TEMPLATE.format(
                        context=context, question=question
                    ),
                }
            ],
        )
        full = msg.content[0].text.strip()
        answer = extract_final(full)

        results.append(
            {
                "uid": str(row.get("uid", i)),
                "difficulty": str(row.get("difficulty", "")),
                "question": question,
                "expected_answer": expected,
                "gold_sources": gold_sources,
                "generated_answer": answer,      # clean value -> compute_metrics
                "generated_full": full,          # kept for transparency/debugging
                "filter_years": years,           # what the metadata filter allowed
                "retrieved": [
                    {
                        "rank": rank + 1,
                        "source": c["source"],
                        "year": c["year"],
                        "month": c["month"],
                        "chunk_index": c["chunk_index"],
                        "distance": c["distance"],
                        "text": c["text"],
                    }
                    for rank, c in enumerate(ranked)
                ],
            }
        )
        print(f"[{i + 1}/{len(df)}] years={years} {question[:55]}... -> {answer[:40]}")

    os.makedirs("results", exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results to {OUT_PATH}")
    print("Next: python compute_metrics.py results/engineered_results.json")


if __name__ == "__main__":
    main()
