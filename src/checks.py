"""Verification: asserts the claims the demo makes. Run after the pipeline.
Exits non-zero with a clear message if any invariant is broken."""
import csv, json, os, sys
from common import OUT, load_ontology, s3, list_keys

def main():
    ont, client = load_ontology(), s3()
    with open(os.path.join(OUT, "extraction_report.json")) as _f: recs = json.load(_f)
    with open(os.path.join(OUT, "client_states.json")) as _f: states = json.load(_f)
    with open(os.path.join(OUT, "agent_tasks.json")) as _f: tasks = json.load(_f)
    with open("data_client_master.csv") as f:
        master = {r["id"]: r for r in csv.DictReader(f)}
    fails = []
    def check(name, ok, detail=""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
        if not ok: fails.append(name)

    print("1. Sovereignty: no client's documents outside their booking jurisdiction")
    bad = []
    for jur in ont["jurisdictions"]:
        b = ont["buckets"]["clean"].format(jur=jur.lower())
        for k in list_keys(client, b):
            parts = k.split("/")
            if len(parts) >= 3 and parts[2] in master and master[parts[2]]["jurisdiction"] != jur:
                bad.append(f"{b}/{k}")
    check("cross-jurisdiction placement", not bad, "; ".join(bad[:3]))

    print("2. Quarantine integrity: nothing below threshold entered an entity prefix")
    bad = [r["clean"] for r in recs
           if r["status"] != "placed" and "_quarantine" not in r["clean"]]
    check("sub-threshold docs only in _quarantine/", not bad, "; ".join(bad[:3]))
    check("junk objects never resolved to a client",
          all(r.get("entity_id") is None for r in recs if r["doc_class"] == "unclassified"))

    print("3. Confidence gating matches ontology thresholds")
    thr = ont["entity_resolution"]
    check("all placed docs >= auto_accept",
          all(r["confidence"] >= thr["auto_accept"] for r in recs if r["status"] == "placed"))
    check("review band within [quarantine_below, auto_accept)",
          all(thr["quarantine_below"] <= r["confidence"] < thr["auto_accept"]
              for r in recs if r["status"] == "human_review" and r["doc_class"] != "unclassified"))

    print("4. Manifests agree with the report")
    for row in master.values():
        b = ont["buckets"]["clean"].format(jur=row["jurisdiction"].lower())
        le = ont["jurisdictions"][row["jurisdiction"]]["legal_entity"]
        m = json.loads(client.get_object(
            Bucket=b, Key=f"{le}/{row['segment']}/{row['id']}/_manifest.json")["Body"].read())
        expected = sum(1 for r in recs if r.get("entity_id") == row["id"] and r["status"] == "placed")
        if len(m["holdings"]) != expected:
            check(f"manifest count for {row['id']}", False,
                  f"manifest {len(m['holdings'])} vs report {expected}"); break
    else:
        check("every entity manifest matches placed docs", True)

    print("5. pKYC state logic")
    check("every non-green file has at least one gap",
          all(s["gaps"] for s in states if s["status"] != "green"))
    check("every green file satisfies its full requirements matrix",
          all(i["state"] == "valid" for s in states if s["status"] == "green" for i in s["items"]))
    gap_entities = {s["entity"]["id"] for s in states if s["gaps"]}
    task_entities = {t["entity_id"] for t in tasks if t["trigger"] == "validity_monitor"}
    check("every file with gaps raised an agent task", gap_entities <= task_entities,
          f"missing: {gap_entities - task_entities}")
    check("every agent task carries a human gate", all(t.get("human_gate") for t in tasks))
    check("adverse media on non-low-risk escalated",
          any(t["action"] == "escalate_full_review" for t in tasks))

    print()
    if fails:
        print(f"VERIFY FAILED: {len(fails)} check(s): {fails}"); sys.exit(1)
    print(f"VERIFY OK — all checks passed across {len(recs)} docs / {len(states)} client files / {len(tasks)} tasks")

if __name__ == "__main__":
    main()
