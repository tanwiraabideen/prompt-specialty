#!/usr/bin/env python3
"""

AI generated as this isn't really part of the scope of the project.

Synthetic training data generator for symptom-to-specialty routing.

You own the CONTENT decisions (axis values, N per call, generation prompt wording).
This script owns the PLUMBING (looping, checkpointing, dedup, leakage checks, splits).

Commands
--------
  python3 generate_synthetic.py make-defs      # parse definitions .md -> bucket_definitions.json
  python3 generate_synthetic.py plan           # show what would run, no API calls
  python3 generate_synthetic.py generate --dry-run   # fake responses, tests the whole pipeline free
  python3 generate_synthetic.py generate       # the real thing
  python3 generate_synthetic.py postprocess    # dedup + leakage check + split

Resumable: generate writes one JSONL line per completed call and skips keys already done.
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import product
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ----------------------------------------------------------------------------
# CONFIG - your decisions live here
# ----------------------------------------------------------------------------

CFG = {
    "taxonomy_csv":      "taxonomy_v1.csv",
    "definitions_md":    "taxonomy_v1_definitions.md",
    "definitions_json":  "bucket_definitions.json",
    "dev_csv":           "dev_set.csv",
    "eval_csv":          "eval_items_BLANK.csv",

    "raw_jsonl":         "synth/raw_calls.jsonl",     # checkpoint, one line per API call
    "examples_jsonl":    "synth/examples.jsonl",      # flattened, one line per example
    "train_jsonl":       "synth/train.jsonl",
    "val_jsonl":         "synth/val.jsonl",

    # Generate with a DIFFERENT model family than your zero-shot baseline.
    # Shared bias between generator and baseline weakens the comparison.
    "gen_model":         "gpt-5.6-sol",
    "base_url":          os.environ.get("GEN_BASE_URL") or None,
    "api_key_env":       "OPENAI_API_KEY",

    "gen_prompt_version": "synthgen_v003",

    # generation doesn't need reasoning, and it slows down / costs more on reasoning-family models
    "reasoning_effort":  "none",

    # HIGH temperature here. Opposite of classification. You want variety.
    "temperature":       1.0,
    "max_tokens":        1500,

    "n_per_call":        15,      # examples requested per API call
    "combos_per_bucket": 8,       # axis combinations sampled per bucket
    "seed":              20260819,

    "max_workers":       6,
    "max_retries":       5,

    "val_fraction":      0.10,
    "near_dup_jaccard":  0.85,    # within-bucket near-duplicate threshold

    "opening_word_warn":  0.40,   # flag a bucket if >40% of items share a first word
}

# Axis values. Edit these. They are the main lever on data diversity.
AXES = {
    "register":    ["formal", "casual", "whatsapp shorthand", "non-native english"],
    "length":      ["2 to 5 words", "one sentence", "two or three sentences"],
    "person":      ["first person", "about a family member"],
    "specificity": ["vague, no duration or detail", "detailed, includes duration"],
    "noise":       ["clean spelling and punctuation", "no punctuation and occasional typos"],
}

GEN_PROMPT = """You are generating training data for a symptom-to-specialty routing classifier used by a medical appointment booking app in the United Arab Emirates.

Generate exactly {n} DISTINCT examples of how a patient might describe a problem that should be routed to this specialty:

SPECIALTY: {bucket}
SCOPE: {scope}

## Closest neighbouring specialties, stay out of these
{near_misses}

## Every other specialty in the system, also stay out of these
An example must clearly belong to {bucket} and NOT plausibly fit any of the following:
{other_buckets}

## Constraints for this batch, follow all of them
- Register: {register}
- Length: {length}
- Person: {person}
- Specificity: {specificity}
- Spelling and punctuation: {noise}

## Rules

WRITE ONLY WHAT THE PERSON FEELS OR OBSERVES.
- Never speculate about the cause, the organ involved, or which doctor is needed.
- Forbidden: "I think it is my heart", "my circulation is not good", "maybe it is my
  thyroid", "I need a skin doctor", "I feel my blood pressure is high".
- Allowed: plain bodily description of the sensation, including everyday phrases people
  really use, such as "my heart is racing" or "my chest feels tight".
- Never name a diagnosis, disease, test, scan, or medication.

FORMAT.
- Each example is ONE SINGLE LINE. No line breaks inside an example. If the length
  setting asks for two or three sentences, separate them with full stops or spaces,
  never a newline.
- Do not number them, label them, or add any commentary.

VARIETY. This is the constraint most often broken. Take it seriously.
- SYNTACTIC OPENINGS: at most 3 of the {n} examples may begin with the word "I".
  Vary how each one opens. Use a mix of: the body part first ("ankles swollen by
  evening"), the trigger first ("after climbing stairs my chest feels tight"), a time
  reference first ("since last week there is a pulling in my calf"), a bare fragment
  with no verb ("chest tight when walking fast"), and a question ("is it normal that
  my legs ache after walking").
- Do not reuse the same two-clause shape (a sensation followed by how it makes them
  feel) more than three times.
- SCOPE COVERAGE: spread the {n} examples across ALL the distinct areas named in the
  SCOPE line above. No single area may account for more than a third of the examples.
- Vary the body site and the wording as well as the sentence shape.
- Write as a real patient would type into a search box on their phone, not as a doctor
  would write in notes. Real search text is often clipped and ungrammatical.

Return ONLY a JSON array of {n} strings. No markdown fences, no other keys.
"""


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------

def load_buckets(path):
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    buckets = sorted({
        r["bucket"].strip()
        for r in rows
        if r["routable"].strip().lower() == "true"
    })
    if len(buckets) != 24:
        raise SystemExit(f"expected 24 routable buckets, got {len(buckets)}: {buckets}")
    return buckets


def parse_definitions_md(path):
    """Extract scope / in-examples / near-misses from the definitions markdown."""
    text = Path(path).read_text(encoding="utf-8")
    # only the bucket definition section
    if "## 2. Bucket definitions" in text:
        text = text.split("## 2. Bucket definitions", 1)[1].split("\n---\n", 1)[0]

    defs = {}
    blocks = re.split(r"^### ", text, flags=re.M)[1:]
    for block in blocks:
        lines = block.strip().split("\n")
        name = lines[0].strip()
        scope, ins, nms = "", [], []
        for ln in lines[1:]:
            ln = ln.strip()
            m = re.match(r"\*\*Scope:\*\*\s*(.+)", ln)
            if m:
                scope = m.group(1).strip()
                continue
            m = re.match(r"-\s*In:\s*(.+)", ln)
            if m:
                ins.append(m.group(1).strip().strip('"'))
                continue
            m = re.match(r"-\s*Near-miss:\s*(.+)", ln)
            if m:
                raw = m.group(1).strip()
                parts = re.split(r"\s*(?:\u2192|->)\s*", raw)
                nms.append({
                    "text": parts[0].strip().strip('"'),
                    "goes_to": parts[1].strip() if len(parts) > 1 else "",
                })
        if scope:
            defs[name] = {"scope": scope, "in_examples": ins, "near_misses": nms}
    return defs


def cmd_make_defs(args):
    defs = parse_definitions_md(CFG["definitions_md"])
    buckets = load_buckets(CFG["taxonomy_csv"])
    missing = [b for b in buckets if b not in defs]
    extra = [b for b in defs if b not in buckets]
    Path(CFG["definitions_json"]).write_text(
        json.dumps(defs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {CFG['definitions_json']} with {len(defs)} buckets")
    print("missing from definitions:", missing or "none")
    print("in definitions but not taxonomy:", extra or "none")
    if missing:
        print("\nFIX THESE BEFORE GENERATING. A bucket with no scope line gets no data.")


def load_definitions():
    p = Path(CFG["definitions_json"])
    if not p.exists():
        raise SystemExit(f"{p} not found. Run: python3 generate_synthetic.py make-defs")
    return json.loads(p.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# Planning
# ----------------------------------------------------------------------------

def build_plan(buckets):
    """Sample axis combinations per bucket. Fixed seed -> reproducible."""
    all_combos = [dict(zip(AXES, vals)) for vals in product(*AXES.values())]
    rng = random.Random(CFG["seed"])
    plan = []
    for bucket in buckets:
        chosen = rng.sample(all_combos, min(CFG["combos_per_bucket"], len(all_combos)))
        for i, combo in enumerate(chosen):
            plan.append({"bucket": bucket, "combo_id": f"{bucket}::{i}", **combo})
    return plan


def render_prompt(task, defs):
    d = defs[task["bucket"]]
    nm = "\n".join(
        f"- {x['text']}" + (f" (belongs to {x['goes_to']})" if x["goes_to"] else "")
        for x in d["near_misses"]
    ) or "- (none listed)"
    others = "\n".join(
        f"- {b}: {defs[b]['scope']}"
        for b in sorted(defs) if b != task["bucket"]
    )
    return GEN_PROMPT.format(
        n=CFG["n_per_call"],
        bucket=task["bucket"],
        scope=d["scope"],
        near_misses=nm,
        other_buckets=others,
        register=task["register"],
        length=task["length"],
        person=task["person"],
        specificity=task["specificity"],
        noise=task["noise"],
    )


def cmd_plan(args):
    buckets = load_buckets(CFG["taxonomy_csv"])
    defs = load_definitions()
    plan = build_plan(buckets)
    print(f"buckets:            {len(buckets)}")
    print(f"combos per bucket:  {CFG['combos_per_bucket']}")
    print(f"examples per call:  {CFG['n_per_call']}")
    print(f"total API calls:    {len(plan)}")
    print(f"target examples:    {len(plan) * CFG['n_per_call']}")
    print(f"\n--- sample rendered prompt ({plan[0]['combo_id']}) ---\n")
    print(render_prompt(plan[0], defs))


# ----------------------------------------------------------------------------
# Generation
# ----------------------------------------------------------------------------

def load_done_keys(path):
    done = set()
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                    if "error" not in rec:          # failed calls must be retried
                        done.add(rec["combo_id"])
                except Exception:
                    pass
    return done


def parse_array(raw):
    """Model returns a JSON array of strings. Be forgiving about fences."""
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    start, end = s.find("["), s.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array found")
    items = json.loads(s[start:end + 1])
    # collapse any embedded newlines: users type into a single-line search box
    out = [re.sub(r"\s+", " ", str(x)).strip()
           for x in items if isinstance(x, (str, int, float)) and str(x).strip()]
    if not out:
        raise ValueError("array parsed but empty")
    return out


def fake_response(task):
    """Dry-run stand-in. Lets you exercise the whole pipeline for free."""
    b = task["bucket"]
    return [f"[dry-run {b} {task['register']} #{i}] placeholder symptom text"
            for i in range(CFG["n_per_call"])]


def call_model(client, prompt):
    resp = client.chat.completions.create(
        model=CFG["gen_model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=CFG["temperature"],
        max_completion_tokens=CFG["max_tokens"],
        reasoning_effort=CFG["reasoning_effort"],
    )
    usage = getattr(resp, "usage", None)
    return resp.choices[0].message.content, {
        "in_tokens": getattr(usage, "prompt_tokens", None),
        "out_tokens": getattr(usage, "completion_tokens", None),
    }


def run_one(client, task, defs, dry_run):
    prompt = render_prompt(task, defs)
    t0 = time.time()
    last_err = None
    for attempt in range(CFG["max_retries"]):
        try:
            if dry_run:
                texts, usage = fake_response(task), {"in_tokens": 0, "out_tokens": 0}
            else:
                raw, usage = call_model(client, prompt)
                texts = parse_array(raw)
            return {
                "combo_id": task["combo_id"],
                "bucket": task["bucket"],
                "axes": {k: task[k] for k in AXES},
                "texts": texts,
                "n_returned": len(texts),
                "gen_model": "dry-run" if dry_run else CFG["gen_model"],
                "gen_prompt_version": CFG["gen_prompt_version"],
                "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:12],
                "retries": attempt,
                "latency_s": round(time.time() - t0, 2),
                **usage,
            }
        except Exception as e:                       # noqa: BLE001
            last_err = e
            time.sleep(min(2 ** attempt, 30))
    return {"combo_id": task["combo_id"], "bucket": task["bucket"],
            "error": f"{type(last_err).__name__}: {last_err}"}


def cmd_generate(args):
    buckets = load_buckets(CFG["taxonomy_csv"])
    defs = load_definitions()
    missing = [b for b in buckets if b not in defs]
    if missing:
        raise SystemExit(f"no definition for: {missing}")

    plan = build_plan(buckets)
    Path(CFG["raw_jsonl"]).parent.mkdir(parents=True, exist_ok=True)
    done = load_done_keys(CFG["raw_jsonl"])
    todo = [t for t in plan if t["combo_id"] not in done]

    if args.only_bucket:
        todo = [t for t in todo if t["bucket"] == args.only_bucket]
    if args.limit:
        todo = todo[:args.limit]

    print(f"planned {len(plan)} calls, {len(done)} already done, running {len(todo)}")
    if not todo:
        return

    client = None
    if not args.dry_run:
        if CFG["gen_model"] == "REPLACE_ME":
            raise SystemExit("set CFG['gen_model']")
        from openai import OpenAI
        client = OpenAI(api_key=os.environ[CFG["api_key_env"]], base_url=CFG["base_url"])

    errors = 0
    with open(CFG["raw_jsonl"], "a", encoding="utf-8") as out, \
         ThreadPoolExecutor(max_workers=CFG["max_workers"]) as pool:
        futs = {pool.submit(run_one, client, t, defs, args.dry_run): t for t in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()                              # checkpoint every call
            if "error" in rec:
                errors += 1
                print(f"  [{i}/{len(todo)}] FAIL {rec['combo_id']}: {rec['error']}")
            elif i % 10 == 0:
                print(f"  [{i}/{len(todo)}] ok")

    print(f"done. errors: {errors}. re-run the same command to retry failures.")


# ----------------------------------------------------------------------------
# Postprocess: flatten, dedup, leakage check, split
# ----------------------------------------------------------------------------

def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def tokens(s):
    return set(norm(s).split())


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def load_reference_texts():
    import csv
    ref = set()
    for path in (CFG["dev_csv"], CFG["eval_csv"]):
        p = Path(path)
        if not p.exists():
            print(f"  WARNING: {path} not found, leakage check incomplete")
            continue
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ref.add(norm(r["symptom_text"]))
    return ref


def cmd_postprocess(args):
    raw = [json.loads(l) for l in Path(CFG["raw_jsonl"]).read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = [r for r in raw if "error" not in r]
    print(f"calls: {len(raw)} total, {len(ok)} successful, {len(raw)-len(ok)} failed")

    rows = []
    for r in ok:
        for t in r["texts"]:
            rows.append({"text": t, "bucket": r["bucket"], **r["axes"],
                         "combo_id": r["combo_id"], "gen_model": r["gen_model"],
                         "gen_prompt_version": r["gen_prompt_version"]})
    print(f"raw examples: {len(rows)}")

    # 1. exact dedup on normalised text
    seen, staged = set(), []
    for row in rows:
        k = norm(row["text"])
        if k and k not in seen:
            seen.add(k)
            staged.append(row)
    print(f"after exact dedup: {len(staged)}  (-{len(rows)-len(staged)})")

    # 2. within-bucket near-duplicate removal
    by_bucket = defaultdict(list)
    for row in staged:
        by_bucket[row["bucket"]].append(row)
    kept = []
    for bucket, items in by_bucket.items():
        keep_toks = []
        for row in items:
            tk = tokens(row["text"])
            if any(jaccard(tk, kt) >= CFG["near_dup_jaccard"] for kt in keep_toks):
                continue
            keep_toks.append(tk)
            kept.append(row)
    print(f"after near-dup removal: {len(kept)}  (-{len(staged)-len(kept)})")

    # 3. leakage check against dev and eval
    ref = load_reference_texts()
    leaked = [r for r in kept if norm(r["text"]) in ref]
    if leaked:
        print(f"\n!!! LEAKAGE: {len(leaked)} training examples appear in dev/eval:")
        for r in leaked[:10]:
            print("   ", r["text"])
        raise SystemExit("refusing to write. remove these before training.")
    print("leakage check: clean")

    # 4. class balance report
    c = Counter(r["bucket"] for r in kept)
    buckets = load_buckets(CFG["taxonomy_csv"])
    print("\nper-bucket counts:")
    for b in buckets:
        flag = "   <- THIN" if c[b] < CFG["n_per_call"] * CFG["combos_per_bucket"] * 0.6 else ""
        print(f"  {b:22} {c[b]:>4}{flag}")
    empty = [b for b in buckets if c[b] == 0]
    if empty:
        raise SystemExit(f"buckets with zero examples: {empty}")

    # 4b. opening-word diversity. Catches the generator getting stuck on one
    #     sentence shape ("I feel ...") across thousands of examples.
    print("\nopening-word concentration (most common first word per bucket):")
    worst = []
    for b in buckets:
        items = [r["text"] for r in kept if r["bucket"] == b]
        if not items:
            continue
        firsts = Counter(norm(t).split()[0] if norm(t).split() else "" for t in items)
        word, n = firsts.most_common(1)[0]
        pct = n / len(items)
        hot = pct > CFG["opening_word_warn"]
        if hot:
            worst.append((b, word, pct))
        print(f"  {b:22} '{word}' {pct:.0%}" + ("   <- TOO CONCENTRATED" if hot else ""))
    if worst:
        print(f"\n  {len(worst)} bucket(s) above {CFG['opening_word_warn']:.0%}. The generator is")
        print("  stuck in one sentence shape. Strengthen the VARIETY block and regenerate,")
        print("  or accept it and record the limitation in your writeup.")

    # 5. stratified split
    rng = random.Random(CFG["seed"])
    train, val = [], []
    for bucket in by_bucket:
        items = [r for r in kept if r["bucket"] == bucket]
        rng.shuffle(items)
        n_val = max(1, int(len(items) * CFG["val_fraction"]))
        val.extend(items[:n_val])
        train.extend(items[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)

    for path, data in ((CFG["train_jsonl"], train), (CFG["val_jsonl"], val)):
        with open(path, "w", encoding="utf-8") as f:
            for row in data:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nwrote {CFG['train_jsonl']} ({len(train)}) and {CFG['val_jsonl']} ({len(val)})")

    print("\nNEXT: read 50 random training rows by hand before you train on any of this.")
    print("      python3 generate_synthetic.py sample --n 50")


def cmd_sample(args):
    rows = [json.loads(l) for l in Path(CFG["train_jsonl"]).read_text(encoding="utf-8").splitlines() if l.strip()]
    rng = random.Random()
    for r in rng.sample(rows, min(args.n, len(rows))):
        print(f"[{r['bucket']:20}] {r['text']}")


# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("make-defs")
    sub.add_parser("plan")
    g = sub.add_parser("generate")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--only-bucket")
    g.add_argument("--limit", type=int)
    sub.add_parser("postprocess")
    s = sub.add_parser("sample")
    s.add_argument("--n", type=int, default=50)
    args = ap.parse_args()

    {"make-defs": cmd_make_defs, "plan": cmd_plan, "generate": cmd_generate,
     "postprocess": cmd_postprocess, "sample": cmd_sample}[args.cmd](args)


if __name__ == "__main__":
    main()