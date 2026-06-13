"""Pipeline: raw swamp -> classify/extract -> entity-resolve -> clean zone.
Uses the Anthropic API when ANTHROPIC_API_KEY is set; falls back to a
deterministic heuristic extractor so the demo runs anywhere."""
import csv, json, os, re, difflib, urllib.request
from common import load_ontology, s3, list_keys, put_json, save_out

CLASS_HINTS = {
    "identity": ["PASSPORT", "PA55PORT"],
    "incorporation": ["INCORPORATION", "REGULATORY AUTHORITY"],
    "ownership_control": ["BENEFICIAL OWNERSHIP", "UBO"],
    "financials": ["FINANCIAL STATEMENTS", "AUDITOR"],
    "facility_docs": ["FACILITY AGREEMENT", "Borrower"],
    "address_proof": ["UTILITY STATEMENT", "Service Address"],
    "correspondence": ["Re:", "Dear Sir"],
}
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

def heuristic_extract(text):
    scores = {c: sum(h.lower() in text.lower() for h in hints) for c, hints in CLASS_HINTS.items()}
    doc_class = max(scores, key=scores.get) if max(scores.values()) else "unclassified"
    party = None
    for label in ["Name:", "Account Holder:", "Borrower:", "Entity:", "For:", "that ", "we refer to "]:
        m = re.search(re.escape(label) + r"\s*(.+)", text)
        if m:
            party = m.group(1).split(" was incorporated")[0].strip(" .")
            break
    dates = DATE.findall(text)
    expiry = (re.search(r"Expiry:\s*(\d{4}-\d{2}-\d{2})", text) or [None, None])[1]
    issue = next((x for x in dates if x != expiry), None)
    return {"doc_class": doc_class, "party": party, "issue_date": issue,
            "expiry_date": expiry, "method": "heuristic"}

def claude_extract(text, key):
    classes = ", ".join(CLASS_HINTS) + ", unclassified"
    prompt = (f"Extract from this bank document. Respond ONLY with JSON, no markdown: "
              f'{{"doc_class": one of [{classes}], "party": primary client/holder name or null, '
              f'"issue_date": "YYYY-MM-DD" or null, "expiry_date": "YYYY-MM-DD" or null}}\n\n{text[:4000]}')
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": "claude-sonnet-4-6", "max_tokens": 300,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    body = json.loads(urllib.request.urlopen(req, timeout=60).read())
    raw = body["content"][0]["text"].strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    out = json.loads(m.group(1) if m else raw)
    out["method"] = "claude"
    return out

def norm(s):  # undo common OCR substitutions, strip legal-form noise
    s = (s or "").lower().replace("rn", "m").replace("0", "o").replace("1", "l").replace("5", "s")
    s = re.sub(r"[^a-z ]", " ", s)
    for w in ["pte", "ltd", "private", "limited", "pvt", "m s", "the"]:
        s = re.sub(rf"\b{w}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def resolve(party, master):
    """Return (entity_id, confidence) against the client master."""
    if not party: return None, 0.0
    p, best = norm(party), (None, 0.0)
    for row in master:
        cand = norm(row["legal_name"])
        score = difflib.SequenceMatcher(None, p, cand).ratio()
        toks_p, toks_c = set(p.split()), set(cand.split())
        if toks_p and toks_p <= toks_c | {"asia", "india", "holdings"}:  # reordered/subset names
            score = max(score, 0.90 + 0.05 * (toks_p == toks_c))
        if score > best[1]: best = (row, score)
    return best

def main():
    ont, client = load_ontology(), s3()
    key = os.environ.get("ANTHROPIC_API_KEY")
    with open("data_client_master.csv") as f:
        master = list(csv.DictReader(f))
    thr = ont["entity_resolution"]
    records = []
    for jur, jconf in ont["jurisdictions"].items():
        raw_b = ont["buckets"]["raw"].format(jur=jur.lower())
        clean_b = ont["buckets"]["clean"].format(jur=jur.lower())
        for k in list_keys(client, raw_b, "legacy/"):
            text = client.get_object(Bucket=raw_b, Key=k)["Body"].read().decode()
            try:
                ex = claude_extract(text, key) if key else heuristic_extract(text)
            except Exception as e:
                print(f"  extract fallback for {k}: {e}"); ex = heuristic_extract(text)
            row, conf = resolve(ex.get("party"), master)
            rec = {"raw": f"{raw_b}/{k}", "jurisdiction": jur, **ex, "confidence": round(conf, 3)}
            doc_id = "d" + str(abs(hash(k)) % 10**6)
            le = jconf["legal_entity"]
            if row and conf >= thr["auto_accept"] and ex["doc_class"] != "unclassified":
                yyyy = (ex.get("issue_date") or "0000")[:4]
                ck = ont["key_schema"][row["segment"]].format(
                    legal_entity=le, entity_id=row["id"], doc_class=ex["doc_class"],
                    yyyy=yyyy, doc_id=doc_id)
                rec |= {"entity_id": row["id"], "status": "placed", "clean": f"{clean_b}/{ck}"}
            else:
                ck = ont["key_schema"]["quarantine"].format(legal_entity=le, doc_id=doc_id)
                if ex["doc_class"] == "unclassified":
                    rec |= {"entity_id": None, "status": "quarantined", "clean": f"{clean_b}/{ck}"}
                else:
                    rec |= {"entity_id": row["id"] if row and conf >= thr["quarantine_below"] else None,
                            "status": "human_review" if conf >= thr["quarantine_below"] else "quarantined",
                            "clean": f"{clean_b}/{ck}"}
            client.put_object(Bucket=clean_b, Key=ck, Body=text.encode())
            records.append(rec)

    # holdings manifest per entity + group manifests (pointers, not paths)
    for row in master:
        jur = row["jurisdiction"]; clean_b = ont["buckets"]["clean"].format(jur=jur.lower())
        le = ont["jurisdictions"][jur]["legal_entity"]
        docs = [r for r in records if r.get("entity_id") == row["id"] and r["status"] == "placed"]
        put_json(client, clean_b, f"{le}/{row['segment']}/{row['id']}/_manifest.json",
                 {"entity": row, "holdings": docs})
    for grp in sorted({r["group"] for r in master if r["group"]}):
        members = [r for r in master if r["group"] == grp]
        jur = members[0]["jurisdiction"]
        put_json(client, ont["buckets"]["clean"].format(jur=jur.lower()),
                 f"{ont['jurisdictions'][jur]['legal_entity']}/CIB/_groups/{grp}.json",
                 {"group": grp, "members": [m["id"] for m in members]})

    save_out("extraction_report.json", records)
    placed = sum(r["status"] == "placed" for r in records)
    print(f"pipeline done: {len(records)} docs | {placed} placed | "
          f"{sum(r['status']=='human_review' for r in records)} human-review | "
          f"{sum(r['status']=='quarantined' for r in records)} quarantined | "
          f"extractor={'claude' if key else 'heuristic'}")

if __name__ == "__main__":
    main()
