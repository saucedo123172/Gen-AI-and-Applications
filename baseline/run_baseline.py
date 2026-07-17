"""
run_baseline.py
---------------
Runs every question in your filtered answer key through the BASELINE system:

  question -> ChromaDB top-5 (pure similarity, no metadata filter)
           -> Claude answers using ONLY the retrieved context
           -> everything logged to results/baseline_results.json

Requires:
  - chroma_db/ built by ingest_baseline.py
  - questions_filtered.csv (your subset of officeqa_full.csv)
  - ANTHROPIC_API_KEY set in your environment:
        export ANTHROPIC_API_KEY="sk-ant-..."

Run:  python run_baseline.py
"""

import json
import os

import chromadb
import pandas as pd
from anthropic import Anthropic

# ----------------------------- config ---------------------------------------
QUESTIONS_CSV = "questions_filtered.csv"
# >>> ADJUST these two to match the actual column names in officeqa_full.csv <<<
QUESTION_COL = "question"
ANSWER_COL = "answer"

DB_DIR = "chroma_db"
COLLECTION = "baseline"
TOP_K = 5
MODEL = "claude-sonnet-4-6"
OUT_PATH = os.path.join("results", "baseline_results.json")
# -----------------------------------------------------------------------------

PROMPT_TEMPLATE = """Answer the question using ONLY the context below.
Give the shortest possible answer (a number, date, or short phrase).
If the answer is not in the context, reply exactly: Not found

Context:
{context}

Question: {question}"""


def main():
    df = pd.read_csv(QUESTIONS_CSV)
    for col in (QUESTION_COL, ANSWER_COL):
        if col not in df.columns:
            raise SystemExit(
                f"Column '{col}' not in {QUESTIONS_CSV}. "
                f"Available columns: {list(df.columns)}\n"
                f"-> Edit QUESTION_COL / ANSWER_COL at the top of this script."
            )

    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection(COLLECTION)
    llm = Anthropic()  # reads ANTHROPIC_API_KEY from environment

    results = []
    for i, row in df.iterrows():
        question = str(row[QUESTION_COL])
        expected = str(row[ANSWER_COL])

        # gold source files from officeqa (cell may contain multiple
        # filenames separated by embedded newlines)
        gold_sources = [
            f.strip()
            for f in str(row.get("source_files", "")).splitlines()
            if f.strip()
        ]

        # ---- retrieve (no filtering: this is the baseline) ----
        r = collection.query(query_texts=[question], n_results=TOP_K)
        docs = r["documents"][0]
        metas = r["metadatas"][0]
        dists = r["distances"][0]

        context = "\n\n---\n\n".join(docs)

        # ---- generate ----
        msg = llm.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT_TEMPLATE.format(
                        context=context, question=question
                    ),
                }
            ],
        )
        answer = msg.content[0].text.strip()

        results.append(
            {
                "uid": str(row.get("uid", i)),
                "difficulty": str(row.get("difficulty", "")),
                "question": question,
                "expected_answer": expected,
                "gold_sources": gold_sources,
                "generated_answer": answer,
                "retrieved": [
                    {
                        "rank": rank + 1,
                        "source": m["source"],
                        "year": m["year"],
                        "month": m["month"],
                        "chunk_index": m["chunk_index"],
                        "distance": d,
                        "text": doc,
                    }
                    for rank, (doc, m, d) in enumerate(zip(docs, metas, dists))
                ],
            }
        )
        print(f"[{i + 1}/{len(df)}] {question[:70]}... -> {answer[:50]}")

    os.makedirs("results", exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results to {OUT_PATH}")
    print("Next: python compute_metrics.py results/baseline_results.json")


if __name__ == "__main__":
    main()
