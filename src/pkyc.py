"""pKYC engine: computes client-file state (holdings vs requirements matrix),
raises validity triggers, runs an event materiality diff, and emits an
agent task queue (the agentic ops layer's work items)."""
import csv, datetime as dt, json
from common import load_ontology, s3, get_json, save_out

TODAY = dt.date(2026, 6, 12)

EVENTS = [  # simulated external feed (registry / adverse media), already entity-resolved
    {"event_id": "EV-001", "type": "registry_ownership_change", "entity_id": "C1001",
     "detail": "ACRA filing: change in shareholders of Meridian Holdings Pte Ltd", "date": "2026-06-09"},
    {"event_id": "EV-002", "type": "adverse_media", "entity_id": "C1006",
     "detail": "Regional news: environmental penalty reported against Sundaram Textile Mills", "date": "2026-06-10"},
]

def age_days(iso):
    return (TODAY - dt.date.fromisoformat(iso)).days if iso else None

def file_state(ont, manifest):
    ent, req = manifest["entity"], ont["requirements"][manifest["entity"]["segment"]]
    required = req[ent["risk"]]
    held = {}
    for h in manifest["holdings"]:
        c = h["doc_class"]
        if c not in held or (h.get("issue_date") or "") > (held[c].get("issue_date") or ""):
            held[c] = h  # latest version wins
    items, gaps = [], []
    for c in required:
        h, conf = held.get(c), ont["doc_classes"][c]
        if not h:
            items.append({"doc_class": c, "state": "missing"}); gaps.append(c); continue
        state, note = "valid", ""
        if conf.get("validity_tracked") and h.get("expiry_date"):
            dleft = -age_days(h["expiry_date"])
            if dleft < 0: state, note = "expired", f"lapsed {-dleft}d ago"
            elif dleft <= ont["pkyc"]["expiry_horizon_days"]: state, note = "expiring", f"{dleft}d left"
        if conf.get("max_age_days") and h.get("issue_date") and age_days(h["issue_date"]) > conf["max_age_days"]:
            state, note = "stale", f"{age_days(h['issue_date'])}d old (max {conf['max_age_days']})"
        if state != "valid": gaps.append(c)
        items.append({"doc_class": c, "state": state, "note": note,
                      "doc": h.get("clean"), "issue_date": h.get("issue_date"),
                      "expiry_date": h.get("expiry_date")})
    extras = [c for c in held if c not in required]
    return {"entity": ent, "items": items, "gaps": gaps, "extras_held": extras,
            "status": "green" if not gaps else "amber" if len(gaps) == 1 else "red"}

def materiality(event, state):
    """The diff engine: what does this event change about the file?"""
    if event["type"] == "registry_ownership_change":
        return {"verdict": "micro_refresh", "scope": ["ownership_control"],
                "why": "ownership document on file predates the registry change; only UBO declaration needs refresh"}
    if event["type"] == "adverse_media":
        return {"verdict": "escalate_full_review" if state["entity"]["risk"] != "low" else "log_only",
                "scope": ["full_file"], "why": "adverse media on a non-low-risk client exceeds micro-refresh threshold"}
    return {"verdict": "log_only", "scope": [], "why": "no impact on required holdings"}

def draft_outreach(ent, gaps):
    return (f"Subject: Document refresh — {ent['legal_name']}\n\n"
            f"Dear client, as part of our ongoing review we require updated copies of: "
            f"{', '.join(gaps)}. All other records we hold remain current — no further "
            f"action is needed on those. [auto-drafted; pending RM approval]")

def main():
    ont, client = load_ontology(), s3()
    with open("data_client_master.csv") as f:
        master = list(csv.DictReader(f))
    states, tasks, tid = [], [], 0
    for row in master:
        b = ont["buckets"]["clean"].format(jur=row["jurisdiction"].lower())
        le = ont["jurisdictions"][row["jurisdiction"]]["legal_entity"]
        st = file_state(ont, get_json(client, b, f"{le}/{row['segment']}/{row['id']}/_manifest.json"))
        states.append(st)
        # internal triggers: validity/staleness -> micro-refresh tasks (this IS pKYC)
        actionable = [i["doc_class"] for i in st["items"] if i["state"] in ("expired", "expiring", "stale", "missing")]
        if actionable:
            tid += 1
            tasks.append({"task_id": f"T-{tid:03d}", "trigger": "validity_monitor",
                          "entity_id": row["id"], "entity": row["legal_name"],
                          "action": "assemble_micro_refresh_pack", "scope": actionable,
                          "human_gate": "RM approves outreach; analyst signs off sufficiency",
                          "outreach_draft": draft_outreach(row, actionable)})
    # external events -> materiality diff -> tasks
    for ev in EVENTS:
        st = next(s for s in states if s["entity"]["id"] == ev["entity_id"])
        m = materiality(ev, st)
        tid += 1
        tasks.append({"task_id": f"T-{tid:03d}", "trigger": ev["type"], "event": ev,
                      "entity_id": ev["entity_id"], "entity": st["entity"]["legal_name"],
                      "action": m["verdict"], "scope": m["scope"], "why": m["why"],
                      "human_gate": "disposition remains with analyst"})
    save_out("client_states.json", states)
    save_out("agent_tasks.json", tasks)
    print(f"pKYC engine: {len(states)} client files | "
          f"{sum(s['status']=='green' for s in states)} green / "
          f"{sum(s['status']=='amber' for s in states)} amber / "
          f"{sum(s['status']=='red' for s in states)} red | {len(tasks)} agent tasks")

if __name__ == "__main__":
    main()
