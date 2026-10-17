"""
Evaluation harness: runs all three retrieval methods in retrieval_methods.py
against eval/test_set.json and reports accuracy (overall and by category)
plus latency for each.

Run with:
    python evaluate.py

Produces:
    eval/results.csv          -- every (method, query) pair with full detail
    eval/summary.csv          -- one row per method: accuracy + latency
    eval/comparison_chart.png -- bar chart of overall accuracy per method

This is the empirical core of the dissertation's RQ1: how do TF-IDF and
embedding-based retrieval compare to the original keyword-matching
approach, and does each extra bit of sophistication actually buy you
anything. Report the summary table and chart directly in your results
chapter, and use eval/results.csv to dig into *which* queries each method
got wrong -- that's your error-analysis section.
"""

import csv
import json
import os
import time

import matplotlib

matplotlib.use("Agg")  # no display needed -- just saves a PNG
import matplotlib.pyplot as plt

from retrieval_methods import METHODS

TEST_SET_PATH = os.path.join("eval", "test_set.json")
RESULTS_PATH = os.path.join("eval", "results.csv")
SUMMARY_PATH = os.path.join("eval", "summary.csv")
CHART_PATH = os.path.join("eval", "comparison_chart.png")


def load_test_set():
    with open(TEST_SET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def is_correct(expected_question, got_question):
    """An out-of-scope query (expected_question is None) is correct only
    if the method also declined to answer. An in-scope query is correct
    only if the method matched the exact right KB entry."""
    if expected_question is None:
        return got_question is None
    return got_question == expected_question


def run_method(method_name, method_cls, test_set):
    print(f"\nLoading method: {method_name} ...")
    instance = method_cls()
    rows = []
    for item in test_set:
        start = time.time()
        answer, matched_question, confidence, source = instance.search(item["query"])
        elapsed = time.time() - start
        correct = is_correct(item["expected_question"], matched_question)
        rows.append(
            {
                "method": method_name,
                "query": item["query"],
                "category": item["category"],
                "expected_question": item["expected_question"] or "",
                "matched_question": matched_question or "",
                "confidence": round(confidence, 3),
                "correct": correct,
                "latency_s": round(elapsed, 4),
            }
        )
    n_correct = sum(r["correct"] for r in rows)
    print(f"  {method_name}: {n_correct}/{len(rows)} correct ({n_correct/len(rows)*100:.1f}%)")
    return rows


def summarize(all_rows):
    methods = sorted(set(r["method"] for r in all_rows))
    categories = sorted(set(r["category"] for r in all_rows))
    summary = []
    for method in methods:
        method_rows = [r for r in all_rows if r["method"] == method]
        overall_acc = sum(r["correct"] for r in method_rows) / len(method_rows)
        avg_latency = sum(r["latency_s"] for r in method_rows) / len(method_rows)
        row = {
            "method": method,
            "overall_accuracy": round(overall_acc, 3),
            "avg_latency_s": round(avg_latency, 4),
        }
        for cat in categories:
            cat_rows = [r for r in method_rows if r["category"] == cat]
            if cat_rows:
                row[f"accuracy_{cat}"] = round(
                    sum(r["correct"] for r in cat_rows) / len(cat_rows), 3
                )
        summary.append(row)
    return summary


def write_csv(path, rows):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def plot_comparison(summary):
    methods = [s["method"] for s in summary]
    accuracies = [s["overall_accuracy"] * 100 for s in summary]
    colors = ["#9095b3", "#e3a857", "#7fd8c6"]

    plt.figure(figsize=(6, 4))
    bars = plt.bar(methods, accuracies, color=colors[: len(methods)])
    plt.ylabel("Overall accuracy (%)")
    plt.title("Retrieval method comparison on UTG test set")
    plt.ylim(0, 100)
    for bar, acc in zip(bars, accuracies):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            acc + 1.5,
            f"{acc:.1f}%",
            ha="center",
            fontsize=9,
        )
    plt.tight_layout()
    plt.savefig(CHART_PATH, dpi=150)
    print(f"\nSaved chart to {CHART_PATH}")


def main():
    os.makedirs("eval", exist_ok=True)

    test_set = load_test_set()
    print(f"Loaded {len(test_set)} test queries "
          f"({sum(1 for t in test_set if t['category'] == 'direct')} direct, "
          f"{sum(1 for t in test_set if t['category'] == 'paraphrase')} paraphrase, "
          f"{sum(1 for t in test_set if t['category'] == 'noisy')} noisy, "
          f"{sum(1 for t in test_set if t['category'] == 'out_of_scope')} out-of-scope).")

    all_rows = []
    for name, cls in METHODS.items():
        try:
            all_rows.extend(run_method(name, cls, test_set))
        except Exception as exc:
            print(f"  {name}: FAILED to run ({exc}). Skipping -- check that its "
                  f"dependencies are installed (see requirements.txt).")

    if not all_rows:
        print("No methods ran successfully -- nothing to report.")
        return

    write_csv(RESULTS_PATH, all_rows)
    print(f"\nWrote per-query results to {RESULTS_PATH}")

    summary = summarize(all_rows)
    write_csv(SUMMARY_PATH, summary)
    print(f"Wrote summary to {SUMMARY_PATH}")

    print("\n=== Summary ===")
    for row in summary:
        print(row)

    plot_comparison(summary)


if __name__ == "__main__":
    main()
