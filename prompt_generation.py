#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

HERE = Path(__file__).parent
load_dotenv(HERE.parent / ".env")

CFG = {
    "taxonomy_csv":    HERE / "taxonomy_v1.csv",
    "definitions_json": HERE / "bucket_definitions.json",
    "system_template": HERE / "prompt_template.txt",
    "user_template":   HERE / "user_prompt_template.txt",
    "log_path":        HERE / "logs" / "requests.jsonl",
    "cache_dir":       HERE / ".cache",

    "expected_all_buckets": 29,   # 24 routable + 5 excluded
    "expected_routable":    24,

    "default_model":    "gpt-5.6-luna",
    "temperature":      0,
    "max_tokens":       200,
    "max_retries":      4,
    "max_workers":      6,
}

EXTRA_OUTPUT_VALUES = {"out_of_scope"}


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

def load_buckets():
    with open(CFG["taxonomy_csv"], newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    all_buckets = {r["bucket"].strip() for r in rows if r["bucket"].strip()}
    routable = sorted({
        r["bucket"].strip() for r in rows
        if r["bucket"].strip() and r["routable"].strip().lower() == "true"
    })

    # HARD FAIL. A silently wrong class list produces plausible wrong numbers,
    # which is the worst possible failure mode for this project.
    if len(all_buckets) != CFG["expected_all_buckets"]:
        raise SystemExit(
            f"taxonomy has {len(all_buckets)} distinct buckets, expected "
            f"{CFG['expected_all_buckets']}. Fix the CSV or update CFG."
        )
    if len(routable) != CFG["expected_routable"]:
        raise SystemExit(
            f"taxonomy has {len(routable)} routable buckets, expected "
            f"{CFG['expected_routable']}: {routable}"
        )
    return routable


def load_definitions():
    p = Path(CFG["definitions_json"])
    if not p.exists():
        raise SystemExit(
            f"{p} not found. Generate it with:\n"
            f"  python3 generate_synthetic.py make-defs"
        )
    return json.loads(p.read_text(encoding="utf-8"))


def build_class_block(buckets, defs, variant):
    """
    variant:
      names  - bucket names only            (weakest, was your original)
      scope  - names + one-line scope
      full   - names + scope + examples + near-misses   (recommended default)
      none   - empty, for a fine-tuned model that knows the label space
    """
    if variant == "none":
        return ""
    if variant == "names":
        return "\n".join(buckets)

    out = []
    for b in buckets:
        d = defs.get(b)
        if not d:
            raise SystemExit(f"no definition for bucket '{b}' in {CFG['definitions_json']}")
        block = [b, f"  Scope: {d['scope']}"]
        if variant == "full":
            for ex in d.get("in_examples", [])[:2]:
                block.append(f'  Belongs here: "{ex}"')
            for nm in d.get("near_misses", []):
                dest = f" (-> {nm['goes_to']})" if nm.get("goes_to") else ""
                block.append(f"  Does NOT belong: {nm['text']}{dest}")
        out.append("\n".join(block))
    return "\n\n".join(out)


def build_prompts(user_text, class_block):
    system_template = Path(CFG["system_template"]).read_text(encoding="utf-8")
    user_template = Path(CFG["user_template"]).read_text(encoding="utf-8")

    system_prompt = system_template.replace("{{CLASS_BLOCK}}", class_block)
    user_prompt = user_template.replace("{{USER_TEXT}}", user_text)

    for name, p in (("system", system_prompt), ("user", user_prompt)):
        if "{{" in p:
            raise SystemExit(f"unsubstituted placeholder left in {name} prompt")
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def make_client(base_url=None):
    # local servers ignore the key but the SDK requires a non-empty string
    return OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY") or "not-needed",
        base_url=base_url,
    )


def cache_key(system_prompt, user_prompt, model, temperature, prompt_version):
    blob = "\x00".join([system_prompt, user_prompt, model,
                        str(temperature), prompt_version])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cache_get(key):
    p = Path(CFG["cache_dir"]) / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def cache_put(key, payload):
    d = Path(CFG["cache_dir"])
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")


def call_model(client, system_prompt, user_prompt, model):
    """Chat completions. Portable across OpenAI, vLLM, Ollama, llama.cpp."""
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=CFG["temperature"],
        max_tokens=CFG["max_tokens"],
    )
    usage = getattr(resp, "usage", None)
    return {
        "text": resp.choices[0].message.content or "",
        "tokens_in": getattr(usage, "prompt_tokens", None),
        "tokens_out": getattr(usage, "completion_tokens", None),
    }


# ---------------------------------------------------------------------------
# Parsing. Three outcomes, tracked separately.
# ---------------------------------------------------------------------------

def parse_response(text, allowed, output_mode):
    """
    Returns (ranked, confidence, status).
    status is one of: ok | invalid_bucket | unparseable
    """
    raw = (text or "").strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    if output_mode == "bare":
        cand = raw.lower().strip().strip('."\'')
        if cand in allowed:
            return [cand], None, "ok"
        return [cand] if cand else [], None, ("invalid_bucket" if cand else "unparseable")

    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return [], None, "unparseable"
    try:
        obj = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return [], None, "unparseable"

    ranked = obj.get("ranked")
    if not isinstance(ranked, list) or not ranked:
        return [], obj.get("confidence"), "unparseable"

    # normalise case and whitespace before comparing, then check membership
    norm = [str(x).strip().lower().replace(" ", "_") for x in ranked]
    status = "ok" if all(b in allowed for b in norm) else "invalid_bucket"
    return norm, obj.get("confidence"), status


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

def log_request(entry):
    p = Path(CFG["log_path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def classify_one(client, item_id, user_text, class_block, allowed, args):
    system_prompt, user_prompt = build_prompts(user_text, class_block)
    key = cache_key(system_prompt, user_prompt, args.model,
                    CFG["temperature"], args.prompt_version)

    cached = None if args.no_cache else cache_get(key)
    if cached:
        result, latency_ms, cache_hit = cached, 0.0, True
    else:
        cache_hit = False
        last_err = None
        result = None
        start = time.perf_counter()
        for attempt in range(CFG["max_retries"]):
            try:
                result = call_model(client, system_prompt, user_prompt, args.model)
                break
            except Exception as e:                      # noqa: BLE001
                last_err = e
                time.sleep(min(2 ** attempt, 20))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        if result is None:
            row = {"item_id": item_id, "symptom_text": user_text,
                   "predicted_bucket": "", "ranked_json": "[]", "confidence": "",
                   "parse_status": "api_error", "tokens_in": "", "tokens_out": "",
                   "latency_ms": latency_ms, "cache_hit": False,
                   "error": f"{type(last_err).__name__}: {last_err}"}
            log_request({**row, "model": args.model,
                         "prompt_version": args.prompt_version,
                         "class_block": args.class_block,
                         "timestamp": datetime.now(timezone.utc).isoformat()})
            return row
        cache_put(key, result)

    ranked, confidence, status = parse_response(result["text"], allowed, args.output_mode)

    row = {
        "item_id": item_id,
        "symptom_text": user_text,
        "predicted_bucket": ranked[0] if ranked else "",
        "ranked_json": json.dumps(ranked),
        "confidence": confidence or "",
        "parse_status": status,
        "tokens_in": result.get("tokens_in") or "",
        "tokens_out": result.get("tokens_out") or "",
        "latency_ms": latency_ms,
        "cache_hit": cache_hit,
        "error": "",
    }
    log_request({**row, "raw_response": result["text"], "model": args.model,
                 "prompt_version": args.prompt_version,
                 "class_block": args.class_block,
                 "timestamp": datetime.now(timezone.utc).isoformat()})
    return row


def get_class_block(args):
    buckets = load_buckets()
    defs = load_definitions() if args.class_block in ("scope", "full") else {}
    allowed = set(buckets) | EXTRA_OUTPUT_VALUES
    return build_class_block(buckets, defs, args.class_block), allowed


def cmd_one(args):
    class_block, allowed = get_class_block(args)
    client = make_client(args.base_url)
    row = classify_one(client, "cli", args.text, class_block, allowed, args)
    print(json.dumps(row, indent=2))


def cmd_batch(args):
    class_block, allowed = get_class_block(args)
    client = make_client(args.base_url)

    with open(args.input, newline="", encoding="utf-8") as f:
        items = list(csv.DictReader(f))
    if args.limit:
        items = items[:args.limit]
    print(f"{len(items)} items | model={args.model} | class_block={args.class_block} "
          f"| output_mode={args.output_mode}")

    rows = []
    with ThreadPoolExecutor(max_workers=CFG["max_workers"]) as pool:
        futs = {
            pool.submit(classify_one, client, it["item_id"], it["symptom_text"],
                        class_block, allowed, args): it
            for it in items
        }
        for i, fut in enumerate(as_completed(futs), 1):
            rows.append(fut.result())
            if i % 10 == 0:
                print(f"  {i}/{len(items)}")

    rows.sort(key=lambda r: r["item_id"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    st = Counter(r["parse_status"] for r in rows)
    n = len(rows)
    print(f"\nwrote {out}")
    print("parse status:")
    for k in ("ok", "invalid_bucket", "unparseable", "api_error"):
        if st[k]:
            print(f"  {k:15} {st[k]:>4}  ({st[k]/n:.0%})")
    bad = st["invalid_bucket"] + st["unparseable"]
    if bad / n > 0.02:
        print(f"\n  format failure rate {bad/n:.0%} is above 2%.")
        print("  Fix the output contract BEFORE reading any accuracy number.")
    live = [r for r in rows if not r["cache_hit"] and r["latency_ms"]]
    if live:
        lat = sorted(r["latency_ms"] for r in live)
        print(f"latency p50 {lat[len(lat)//2]:.0f}ms  "
              f"p95 {lat[int(len(lat)*0.95)-1 if len(lat)>1 else 0]:.0f}ms  "
              f"(n={len(live)} uncached)")
        ti = [int(r["tokens_in"]) for r in live if r["tokens_in"]]
        to = [int(r["tokens_out"]) for r in live if r["tokens_out"]]
        if ti:
            print(f"tokens: in avg {sum(ti)/len(ti):.0f}  out avg {sum(to)/len(to):.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=CFG["default_model"])
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL") or None,
                    help="e.g. http://localhost:8000/v1 for vLLM. Omit for OpenAI.")
    ap.add_argument("--class-block", default="full",
                    choices=["names", "scope", "full", "none"])
    ap.add_argument("--output-mode", default="json", choices=["json", "bare"])
    ap.add_argument("--prompt-version", default=None)
    ap.add_argument("--no-cache", action="store_true")

    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("one"); o.add_argument("text")
    b = sub.add_parser("batch")
    b.add_argument("--input", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--limit", type=int)

    args = ap.parse_args()
    if args.prompt_version is None:
        # version must encode the class-block variant: different block, different prompt
        args.prompt_version = f"zeroshot_v001_cb-{args.class_block}"

    {"one": cmd_one, "batch": cmd_batch}[args.cmd](args)


if __name__ == "__main__":
    main()