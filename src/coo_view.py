"""Render the COO briefing: same pipeline outputs, executive lens.
Plain English, outcomes first, no storage/ML jargon."""
import json, os, html
from common import OUT

C = {"ink": "#1F2933", "mut": "#7B8794", "bg": "#F7F6F3", "card": "#FFFFFF",
     "line": "#E4E2DC", "green": "#1E7A52", "greenbg": "#E7F3ED",
     "amber": "#A4660A", "amberbg": "#FBF1DC", "red": "#B3361C", "redbg": "#F9E8E2",
     "navy": "#1C3D5A"}
F_DISP = "Georgia,'Times New Roman',serif"
F_BODY = "-apple-system,'Segoe UI',Roboto,system-ui,sans-serif"

PLAIN = {  # ops language, not system language
    "identity": "ID document", "address_proof": "Proof of address",
    "incorporation": "Certificate of incorporation", "ownership_control": "Ownership (UBO) declaration",
    "financials": "Audited financials", "facility_docs": "Facility agreement",
    "correspondence": "Correspondence"}
STATE_WORDS = {"expired": "has expired", "expiring": "expires soon",
               "stale": "is out of date", "missing": "not on file"}

def pill(txt, tone):
    return (f'<span style="font:600 12px {F_BODY};color:{C[tone]};background:{C[tone+"bg"]};'
            f'padding:3px 10px;border-radius:99px;white-space:nowrap">{txt}</span>')

def main():
    with open(os.path.join(OUT, "extraction_report.json")) as _f: recs = json.load(_f)
    with open(os.path.join(OUT, "client_states.json")) as _f: states = json.load(_f)
    with open(os.path.join(OUT, "agent_tasks.json")) as _f: tasks = json.load(_f)

    n_clients = len(states)
    ready = [s for s in states if s["status"] == "green"]
    attention = [s for s in states if s["status"] != "green"]
    placed = sum(r["status"] == "placed" for r in recs)
    checking = sum(r["status"] == "human_review" for r in recs)
    valid_held = sum(1 for s in states for i in s["items"] if i["state"] == "valid")
    to_request = sum(len(s["gaps"]) for s in states)
    drafts = sum(1 for t in tasks if t.get("outreach_draft"))
    escalations = [t for t in tasks if t["action"] == "escalate_full_review"]

    # ---- hero ----
    hero = f"""
    <div style="background:{C['navy']};border-radius:10px;padding:34px 36px;color:#fff">
      <div style="font:600 12px {F_BODY};letter-spacing:.14em;text-transform:uppercase;opacity:.75">
        Client file health · this week</div>
      <div style="font:700 40px {F_DISP};margin:10px 0 6px;line-height:1.15">
        {len(ready)} of {n_clients} client files are complete and current —<br>
        without asking the client for anything.</div>
      <div style="font:16px {F_BODY};opacity:.85;max-width:640px">Across the remaining {len(attention)},
        your team only needs to request <b>{to_request} documents</b>. The other
        <b>{valid_held} required documents are already on file</b>, found and verified from the bank's own records.</div>
    </div>"""

    # ---- portfolio health bar ----
    def seg(n, color, label):
        if not n: return ""
        return (f'<div style="flex:{n};background:{color};height:14px"></div>')
    bar = (f'<div style="display:flex;border-radius:99px;overflow:hidden;margin:14px 0 8px">'
           f'{seg(len(ready), C["green"], "")}'
           f'{seg(sum(s["status"]=="amber" for s in states), C["amber"], "")}'
           f'{seg(sum(s["status"]=="red" for s in states), C["red"], "")}</div>'
           f'<div style="font:13px {F_BODY};color:{C["mut"]}">'
           f'<span style="color:{C["green"]};font-weight:700">●</span> {len(ready)} up to date &nbsp;&nbsp;'
           f'<span style="color:{C["amber"]};font-weight:700">●</span> {sum(s["status"]=="amber" for s in states)} need one update &nbsp;&nbsp;'
           f'<span style="color:{C["red"]};font-weight:700">●</span> {sum(s["status"]=="red" for s in states)} need urgent attention</div>')

    # ---- stats row ----
    def stat(n, label, sub=""):
        return (f'<div style="background:{C["card"]};border:1px solid {C["line"]};border-radius:10px;'
                f'padding:18px 20px;flex:1;min-width:150px">'
                f'<div style="font:700 32px {F_DISP};color:{C["ink"]}">{n}</div>'
                f'<div style="font:600 13px {F_BODY};color:{C["ink"]};margin-top:2px">{label}</div>'
                f'<div style="font:12px {F_BODY};color:{C["mut"]};margin-top:2px">{sub}</div></div>')
    stats = (f'<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:16px">'
             + stat(f"{placed} <span style='font-size:18px;color:{C['mut']}'>of {len(recs)}</span>",
                    "documents identified and filed", "automatically, from legacy archives")
             + stat(drafts, "client requests drafted", "waiting for RM approval — nothing sent without sign-off")
             + stat(checking, "document being double-checked", "uncertain match — a person confirms before filing")
             + stat(len(escalations), "case escalated", "external news triggered a full review")
             + '</div>')

    # ---- action list (only clients needing something) ----
    cards = ""
    order = {"red": 0, "amber": 1}
    for s in sorted(attention, key=lambda x: order[x["status"]]):
        e = s["entity"]
        needs = []
        for i in s["items"]:
            if i["state"] != "valid":
                needs.append(f'{PLAIN[i["doc_class"]]} {STATE_WORDS[i["state"]]}')
        t_for_e = [t for t in tasks if t["entity_id"] == e["id"]]
        done_lines = []
        for t in t_for_e:
            if t["action"] == "escalate_full_review":
                done_lines.append("Flagged for full review after an external news alert — routed to the analyst.")
            elif t.get("outreach_draft"):
                done_lines.append("Refresh pack assembled from documents already on file; a client request "
                                  "covering only the missing items is drafted for the RM.")
            elif t["action"] == "micro_refresh":
                done_lines.append("A registry change was detected; only the affected document is queued "
                                  "for refresh — no full review needed.")
        tone = "red" if s["status"] == "red" else "amber"
        label = "Urgent" if s["status"] == "red" else "Action needed"
        cards += (f'<div style="background:{C["card"]};border:1px solid {C["line"]};border-radius:10px;'
                  f'padding:18px 22px;margin-top:12px">'
                  f'<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">'
                  f'<div style="font:700 17px {F_BODY};color:{C["ink"]}">{html.escape(e["legal_name"])}'
                  f' <span style="font:400 13px {F_BODY};color:{C["mut"]}">'
                  f'{ "Corporate" if e["segment"]=="CIB" else "Retail" } · {e["jurisdiction"]} · {e["risk"]} risk</span></div>'
                  f'{pill(label, tone)}</div>'
                  f'<div style="font:14px {F_BODY};color:{C["ink"]};margin-top:8px">'
                  f'{" · ".join(needs)}</div>'
                  + "".join(f'<div style="font:13px {F_BODY};color:{C["green"]};margin-top:6px">'
                            f'✓ &nbsp;{d}</div>' for d in done_lines)
                  + '</div>')


    auto_cards = ""
    green_ids = {s2["entity"]["id"] for s2 in ready}
    for t in tasks:
        if t["entity_id"] in green_ids:
            auto_cards += (f'<div style="background:{C["card"]};border:1px solid {C["line"]};'
                f'border-radius:10px;padding:14px 22px;margin-top:10px;font:14px {F_BODY}">'
                f'<b>{html.escape(t["entity"])}</b> — a company registry change was detected. '
                f'Only the affected ownership document is queued for refresh; the rest of the file '
                f'stays untouched. No full review, no client disruption. '
                f'<span style="color:{C["mut"]};font-size:12px">This is perpetual KYC working: '
                f'events trigger targeted updates instead of calendar-driven full reviews.</span></div>')
    auto_section = (f'<div style="font:700 18px {F_DISP};margin-top:30px">Handled without your team</div>'
                    + auto_cards) if auto_cards else ""

    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>KYC Briefing</title></head>
<body style="margin:0;background:{C['bg']};color:{C['ink']}">
<div style="max-width:880px;margin:0 auto;padding:30px 22px 60px">
  <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:18px">
    <div style="font:700 22px {F_DISP}">Coverage KYC Briefing</div>
    <div style="font:13px {F_BODY};color:{C['mut']}">Week of 12 June 2026 · pilot portfolio, 10 clients</div>
  </div>
  {hero}
  {bar}
  {stats}
  <div style="font:700 18px {F_DISP};margin-top:30px">Where your team is needed</div>
  <div style="font:13px {F_BODY};color:{C['mut']};margin-top:2px">Everything below has been prepared;
    each item waits on a human decision, not on document hunting.</div>
  {cards}
  {auto_section}
  <div style="margin-top:26px;background:{C['greenbg']};border-radius:10px;padding:14px 20px;
       font:13px {F_BODY};color:{C['ink']}">
    <b>Where documents live:</b> records for India-booked clients are stored in India, Singapore-booked in
    Singapore — enforced by where the files physically sit, not by policy memos. Retention clocks and access
    rights follow automatically.</div>
  <div style="margin-top:14px;font:12px {F_BODY};color:{C['mut']}">Pilot on synthetic data ·
    a technical view of the same run is available for the architecture team.</div>
</div></body></html>"""
    path = os.path.join(OUT, "coo_briefing.html")
    with open(path, "w") as _f: _f.write(page)
    print(f"COO briefing written: {path}")

if __name__ == "__main__":
    main()
