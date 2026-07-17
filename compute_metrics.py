"""
compute_metrics.py
------------------
Computes assignment metrics from a results JSON produced by run_baseline.py
(or run_engineered.py -- same log format).

Retrieval correctness uses the GOLD SOURCE FILES from officeqa_full.csv
(the `source_files` column, logged as `gold_sources`):

  A retrieved chunk is "correct" if it comes from one of the question's
  gold bulletin files.

This is doc-level relevance -- the right call for this answer key, because
several answers are COMPUTED values (e.g., a QoQ percent change) that never
appear verbatim in any chunk, so text-matching would falsely score retrieval
as a miss. We still report answer-in-chunk as a supplementary "evidence
rate" for diagnosis.

  Retriever:  Hit Rate@5, MRR  (gold-source based)
  Generator:  Factual Accuracy (exact for text, +/-1% for numbers)

Groundedness / Hallucination Rate need claim-level LLM-as-judge scoring --
run those separately once accuracy looks sane. Recall at doc level equals
Hit Rate when each question has one gold file; for multi-file questions we
report (gold files retrieved) / (gold files total).

Run:  python compute_metrics.py results/baseline_results.json
"""

import json
import re
import sys


# ----------------------- answer matching helpers ----------------------------

NUM_RE = re.compile(r"-?\$?\d[\d,]*\.?\d*%?")


def extract_numbers(text: str):
    """Pull all numeric values out of a string, normalized to floats."""
    nums = []
    for tok in NUM_RE.findall(text):
        clean = tok.replace(",", "").replace("$", "").replace("%", "")
        try:
            nums.append(float(clean))
        except ValueError:
            pass
    return nums


def numbers_match(a: float, b: float, tol: float = 0.01) -> bool:
    """True if within +/-1% (assignment spec)."""
    if b == 0:
        return abs(a) < 1e-9
    return abs(a - b) / abs(b) <= tol


def answer_in_text(expected: str, text: str) -> bool:
    """Supplementary signal: does `text` literally contain the answer?"""
    exp_nums = extract_numbers(expected)
    if exp_nums:
        text_nums = extract_numbers(text)
        return all(any(numbers_match(t, e) for t in text_nums) for e in exp_nums)
    return expected.strip().lower() in text.lower()


def answers_match(expected: str, generated: str) -> bool:
    """Factual accuracy: generated answer vs. answer key (+/-1% numeric)."""
    exp_nums = extract_numbers(expected)
    if exp_nums:
        gen_nums = extract_numbers(generated)
        if not gen_nums:
            return False
        return all(any(numbers_match(g, e) for g in gen_nums) for e in exp_nums)
    return expected.strip().lower() in generated.strip().lower()


# ------------------------------- metrics ------------------------------------

def main(path: str):
    with open(path) as f:
        results = json.load(f)

    n = len(results)
    hits = 0
    rr_sum = 0.0
    recall_sum = 0.0
    evidence_hits = 0
    correct_answers = 0
    rows = []

    for r in results:
        expected = r["expected_answer"]
        gold = set(r.get("gold_sources", []))

        # --- retriever: gold-source based ---
        first_rank = None
        retrieved_gold = set()
        for chunk in r["retrieved"]:
            if chunk["source"] in gold:
                retrieved_gold.add(chunk["source"])
                if first_rank is None:
                    first_rank = chunk["rank"]

        hit = first_rank is not None
        if hit:
            hits += 1
            rr_sum += 1.0 / first_rank
        recall_sum += (len(retrieved_gold) / len(gold)) if gold else 0.0

        # supplementary: did any retrieved chunk literally contain the answer?
        evidence = any(answer_in_text(expected, c["text"]) for c in r["retrieved"])
        if evidence:
            evidence_hits += 1

        # --- generator ---
        correct = answers_match(expected, r["generated_answer"])
        if correct:
            correct_answers += 1

        rows.append(
            {
                "uid": r.get("uid", "?"),
                "difficulty": r.get("difficulty", ""),
                "hit": hit,
                "rank": first_rank,
                "evidence": evidence,
                "correct": correct,
                "expected": expected,
                "generated": r["generated_answer"],
                "question": r["question"],
            }
        )

    print(f"Results file: {path}")
    print(f"Questions:            {n}")
    print(f"Hit Rate@5:           {hits / n:.1%}   (gold source file in top 5)")
    print(f"MRR:                  {rr_sum / n:.2f}")
    print(f"Recall (doc-level):   {recall_sum / n:.1%}   (gold files retrieved / gold files total)")
    print(f"Evidence Rate:        {evidence_hits / n:.1%}   (answer value literally in a retrieved chunk)")
    print(f"Factual Accuracy:     {correct_answers / n:.1%}   (matches answer key, +/-1%)")

    # per-question table -- with a small eval set, look at every row
    print("\nPer-question breakdown:")
    print(f"{'uid':<9}{'diff':<6}{'hit@5':<7}{'rank':<6}{'evid':<6}{'correct':<9}expected -> generated")
    for row in rows:
        print(
            f"{row['uid']:<9}{row['difficulty']:<6}"
            f"{str(row['hit']):<7}{str(row['rank']):<6}"
            f"{str(row['evidence']):<6}{str(row['correct']):<9}"
            f"{row['expected'][:20]} -> {row['generated'][:40]}"
        )

    # failure triage for the "Bottleneck" reflection question
    retr_fail = sum(1 for row in rows if not row["hit"])
    gen_fail = sum(1 for row in rows if row["hit"] and not row["correct"])
    print(f"\nFailure breakdown (for your 'Bottleneck' reflection):")
    print(f"  Retrieval failures (gold file never in top 5):   {retr_fail}")
    print(f"  Generation failures (right file, wrong answer):  {gen_fail}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python compute_metrics.py results/baseline_results.json")
    main(sys.argv[1])
