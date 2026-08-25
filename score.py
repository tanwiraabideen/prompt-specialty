#!/usr/bin/env python3
"""
Scorer. Usage:
  python3 score.py preds/llama1b_scope.csv
  python3 score.py preds/*.csv --table
  python3 score.py preds/llama1b_full.csv --confusion cm.csv
"""
import argparse, json
import pandas as pd
from sklearn.metrics import (accuracy_score, f1_score,
                             classification_report, confusion_matrix)

NOT_CLINICAL = {"emergency", "out_of_scope", "none_of_these"}


def score(pred_path, gold_path, gold_col):
    gold = pd.read_csv(gold_path)[["item_id", gold_col]].rename(columns={gold_col: "gold"})
    df = pd.read_csv(pred_path).merge(gold, on="item_id")
    df["parse_status"] = df.get("parse_status", "ok").fillna("ok")

    ok = df[df.parse_status == "ok"]
    y_true, y_pred = ok.gold.values, ok.predicted_bucket.fillna("").values
    labels = sorted(set(y_true) - NOT_CLINICAL)

    return dict(
        run=pred_path.split("/")[-1].replace(".csv", ""),
        n=len(ok),
        macro_f1=f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0),
        accuracy=accuracy_score(y_true, y_pred),
        top3=ok.apply(lambda r: r.gold in json.loads(r.ranked_json or "[]")[:3], axis=1).mean(),
        parse_ok=(df.parse_status == "ok").mean(),
        gm_rate=(y_pred == "general_medicine").mean(),
        _df=ok, _labels=labels,
    )


def report(r):
    print(f"\n=== {r['run']} ===")
    print(f"parse ok {r['parse_ok']:.0%} | scored {r['n']} items "
          f"(1 item = {1/r['n']:.1%} of accuracy)")
    print(f"macro-F1 {r['macro_f1']:.3f} | accuracy {r['accuracy']:.3f} | "
          f"top-3 {r['top3']:.3f} | general_medicine {r['gm_rate']:.0%} of predictions\n")
    print(classification_report(r["_df"].gold, r["_df"].predicted_bucket,
                                labels=r["_labels"], zero_division=0))
    err = r["_df"][r["_df"].gold != r["_df"].predicted_bucket]
    if len(err):
        print("top confusions (gold -> predicted):")
        print(err.groupby(["gold", "predicted_bucket"]).size()
                 .sort_values(ascending=False).head(8).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("preds", nargs="+")
    ap.add_argument("--gold", default="dev_set.csv")
    ap.add_argument("--gold-col", default="llm_label")
    ap.add_argument("--table", action="store_true")
    ap.add_argument("--confusion")
    a = ap.parse_args()

    results = [score(p, a.gold, a.gold_col) for p in a.preds]

    if a.table:
        t = pd.DataFrame(results).drop(columns=["_df", "_labels"])
        print(t[["run", "n", "macro_f1", "accuracy", "top3", "parse_ok", "gm_rate"]]
              .sort_values("macro_f1", ascending=False).to_string(index=False))
        n = results[0]["n"]
        print(f"\nn={n}. One item is worth {1/n:.1%}, so gaps smaller than "
              f"~{3/n:.0%} are within a few items and should not be called a winner.")
    else:
        for r in results:
            report(r)

    if a.confusion:
        r = results[0]
        labs = sorted(set(r["_df"].gold) | set(r["_df"].predicted_bucket))
        pd.DataFrame(confusion_matrix(r["_df"].gold, r["_df"].predicted_bucket, labels=labs),
                     index=labs, columns=labs).to_csv(a.confusion)
        print(f"\nwrote {a.confusion}")