import argparse
import csv
import json
from pathlib import Path

def main(args):
    FIELDS = ["item_id", "symptom_text", "predicted_bucket",
          "ranked_json", "confidence", "parse_status"]

    with open(args.input, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "item_id": r["item_id"],
                "symptom_text": r["symptom_text"], 
                "predicted_bucket": "general_medicine",
                "ranked_json": json.dumps(["general_medicine"]),
                "confidence": "",
                "parse_status": "ok"
            })

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="dev_set.csv")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    main(args)
