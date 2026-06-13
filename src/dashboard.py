"""Render a self-contained HTML ops console from pipeline outputs.
Ledger-meets-terminal aesthetic: serif masthead, monospace data, the
client-file state board as the signature element."""
import json, os, html
from common import OUT, load_ontology, s3, list_keys

C = {"ink": "#141C26", "mut": "#67737E", "line": "#D8DDE0", "bg": "#F3F5F4", "card": "#FFFFFF",
     "teal": "#0B5C60", "tealbg": "#E3EEEC", "red": "#B83A1B", "redbg": "#F7E6DF",
     "amber": "#9A6B12", "amberbg": "#F5EDDA", "slate": "#5A6470", "slatebg": "#E8EBED"}
STATE = {"valid": ("teal", "■"), "expiring": ("amber", "◪"), "stale": ("amber", "◪"),
         "expired": ("red", "■"), "missing": ("red", "□")}

def chip(txt, tone):
    return (f'<span style="font:600 11px ui-monospace,Consolas,monospace;color:{C[tone]};'
            f'background:{C[tone+"bg"]};padding:2px 7px;border-radius:3px;">{html.escape(txt)}</span>')

def keypath(k):
    parts = k.split("/")
    seps = f'<span style="color:{C["line"]}">/</span>'
    return ('<div style="font:12px ui-monospace,Consolas,monospace;color:%s;padding:6px 0;'
            'border-bottom:1px solid %s;overflow-wrap:anywhere;">%s</div>'
            % (C["ink"], C["line"], seps.join(
                f'<span style="color:{C["teal"]};font-weight:700">{html.escape(p)}</span>'
                if i < 2 else html.escape(p) for i, p in enumerate(parts))))

def main():
    ont = load_ontology()
    with open(os.path.join(OUT, "extraction_report.json")) as _f: recs = json.load(_f)
    with open(os.path.join(OUT, "client_states.json")) as _f: states = json.load(_f)
    with open(os.path.join(OUT, "agent_tasks.json")) as _f: tasks = json.load(_f)
    placed = [r for r in recs if r["status"] == "placed"]
    review = [r for r in recs if r["status"] == "human_review"]
    quar = [r for r in recs if r["status"] == "quarantined"]
    client = s3()
    sample_keys = []
    for jur in ont["jurisdictions"]:
        b = ont["buckets"]["clean"].format(jur=jur.lower())
        sample_keys += [f"{b}/{k}" for k in list_keys(client, b)
                        if "_manifest" not in k and "_quarantine" not in k and "_groups" not in k][:4]

    def stat(n, label, tone="ink"):
        return (f'<div style="min-width:120px;padding-right:18px"><div style="font:700 34px Georgia,serif;color:{C[tone]}">{n}</div>'
                f'<div style="font:11px ui-monospace,monospace;letter-spacing:.12em;'
                f'text-transform:uppercase;color:{C["mut"]}">{label}</div></div>')

    # --- client-file state board (signature element) ---
    all_classes = list(ont["doc_classes"])
    head = "".join(f'<th style="font:10px ui-monospace,monospace;color:{C["mut"]};padding:4px 6px;'
                   f'text-transform:uppercase;letter-spacing:.06em;text-align:center">{c.replace("_","<br>")}</th>'
                   for c in all_classes)
    rows = ""
    for st in states:
        e = st["entity"]
        cells = ""
        by_class = {i["doc_class"]: i for i in st["items"]}
        for c in all_classes:
            i = by_class.get(c)
            if not i:
                mark = ('<span style="color:%s">·</span>' % C["line"]) if c not in st["extras_held"] \
                       else f'<span title="held, not required" style="color:{C["slate"]}">▫</span>'
            else:
                tone, glyph = STATE[i["state"]]
                title = f'{i["state"]} {i.get("note","")}'.strip()
                mark = f'<span title="{html.escape(title)}" style="color:{C[tone]};font-size:15px">{glyph}</span>'
            cells += f'<td style="text-align:center;padding:4px 6px">{mark}</td>'
        tone = {"green": "teal", "amber": "amber", "red": "red"}[st["status"]]
        rows += (f'<tr style="border-top:1px solid {C["line"]}">'
                 f'<td style="padding:7px 8px;font:12px ui-monospace,monospace;color:{C["mut"]}">{e["id"]}</td>'
                 f'<td style="padding:7px 8px;font:13px system-ui;color:{C["ink"]}">{html.escape(e["legal_name"])}'
                 f' <span style="color:{C["mut"]};font-size:11px">{e["jurisdiction"]} · {e["segment"]} · {e["risk"]} risk</span></td>'
                 f'{cells}<td style="text-align:center">{chip(st["status"].upper(), tone)}</td></tr>')

    task_cards = ""
    for t in tasks:
        tone = "red" if t["action"] == "escalate_full_review" else "teal" if "pack" in t["action"] else "slate"
        why = t.get("why") or f'scope: {", ".join(t["scope"])}'
        ev = t.get("event", {}).get("detail", "")
        task_cards += (
            f'<div style="background:{C["card"]};border:1px solid {C["line"]};border-left:3px solid {C[tone]};'
            f'border-radius:4px;padding:12px 14px;margin-bottom:10px">'
            f'<div style="display:flex;gap:10px;align-items:baseline;flex-wrap:wrap">'
            f'<span style="font:700 12px ui-monospace,monospace;color:{C["ink"]}">{t["task_id"]}</span>'
            f'{chip(t["trigger"], "slate")}{chip(t["action"], tone)}'
            f'<span style="font:13px system-ui;color:{C["ink"]}">{html.escape(t["entity"])}</span></div>'
            f'<div style="font:12px system-ui;color:{C["mut"]};margin-top:6px">{html.escape(ev or why)}'
            f'</div><div style="font:11px ui-monospace,monospace;color:{C["teal"]};margin-top:6px">'
            f'human gate · {html.escape(t["human_gate"])}</div></div>')

    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Estate Console — pKYC POC</title></head>
<body style="margin:0;background:{C['bg']};color:{C['ink']}">
<div style="max-width:1060px;margin:0 auto;padding:28px 20px 60px">
  <div style="border-bottom:3px double {C['ink']};padding-bottom:14px;display:flex;
       justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:10px">
    <div>
      <div style="font:11px ui-monospace,monospace;letter-spacing:.18em;color:{C['teal']};
           text-transform:uppercase">Unstructured Data Estate · Clean Zone · Perpetual KYC</div>
      <div style="font:700 30px Georgia,'Times New Roman',serif;margin-top:2px">Estate Console</div>
    </div>
    <div style="font:11px ui-monospace,monospace;color:{C['mut']}">run 2026-06-12 · extractor: {recs[0]['method']} · endpoint: S3-compatible</div>
  </div>

  <div style="display:flex;gap:28px;flex-wrap:wrap;padding:20px 0;border-bottom:1px solid {C['line']}">
    {stat(len(recs), "raw objects scanned")}
    {stat(len(placed), "auto-placed in clean zone", "teal")}
    {stat(len(review), "human review queue", "amber")}
    {stat(len(quar), "quarantined", "red")}
    {stat(sum(s['status']!='green' for s in states), "client files with gaps", "red")}
    {stat(len(tasks), "agent tasks raised", "ink")}
  </div>

  <div style="display:grid;grid-template-columns:1.1fr .9fr;gap:24px;margin-top:24px">
   <div>
    <div style="font:11px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;
         color:{C['mut']};margin-bottom:8px">Clean zone — sovereignty-shaped keys</div>
    <div style="background:{C['card']};border:1px solid {C['line']};border-radius:4px;padding:6px 14px">
      {''.join(keypath(k) for k in sample_keys)}
      <div style="font:11px system-ui;color:{C['mut']};padding:8px 0 4px">bucket-per-jurisdiction · legal entity
      · segment · entity · doc class · year — retention &amp; ACLs attach to prefixes</div>
    </div>
   </div>
   <div>
    <div style="font:11px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;
         color:{C['mut']};margin-bottom:8px">Resolution &amp; lineage</div>
    <div style="background:{C['card']};border:1px solid {C['line']};border-radius:4px;padding:12px 14px;
         font:12px system-ui;color:{C['ink']}">
      Every placement carries <span style="font-family:ui-monospace,monospace">raw key → extraction →
      resolved entity → confidence → clean key</span>.<br><br>
      {chip('auto-accept ≥ .93','teal')} &nbsp;{chip('human review ≥ .72','amber')} &nbsp;{chip('quarantine < .72','red')}
      <div style="margin-top:10px;color:{C['mut']}">{len(review)} document(s) await side-by-side review;
      {len(quar)} object(s) (junk/unresolvable) never entered the clean zone.</div>
    </div>
   </div>
  </div>

  <div style="margin-top:30px">
    <div style="font:11px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;
         color:{C['mut']};margin-bottom:8px">Client file state board — holdings vs requirements matrix</div>
    <div style="background:{C['card']};border:1px solid {C['line']};border-radius:4px;padding:6px 10px;overflow-x:auto">
      <table style="border-collapse:collapse;width:100%"><tr>
        <th style="font:10px ui-monospace,monospace;color:{C['mut']};text-align:left;padding:4px 8px">ID</th>
        <th style="font:10px ui-monospace,monospace;color:{C['mut']};text-align:left;padding:4px 8px">CLIENT</th>
        {head}<th style="font:10px ui-monospace,monospace;color:{C['mut']}">FILE</th></tr>{rows}
      </table>
      <div style="font:11px system-ui;color:{C['mut']};padding:8px">
        <span style="color:{C['teal']}">■</span> valid &nbsp;
        <span style="color:{C['amber']}">◪</span> expiring/stale &nbsp;
        <span style="color:{C['red']}">■</span> expired &nbsp;
        <span style="color:{C['red']}">□</span> missing &nbsp;
        <span style="color:{C['slate']}">▫</span> held, not required &nbsp;·&nbsp; not applicable</div>
    </div>
  </div>

  <div style="margin-top:30px">
    <div style="font:11px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;
         color:{C['mut']};margin-bottom:8px">Agent task queue — validity monitor + event materiality diffs</div>
    {task_cards}
  </div>

  <div style="margin-top:26px;font:11px ui-monospace,monospace;color:{C['mut']};
       border-top:1px solid {C['line']};padding-top:10px">
    POC · synthetic data · layout, retention and access derived from config/ontology.yaml ·
    same code runs against MinIO / any S3 endpoint</div>
</div></body></html>"""
    path = os.path.join(OUT, "dashboard.html")
    with open(path, "w") as _f: _f.write(page)
    print(f"dashboard written: {path}")

if __name__ == "__main__":
    main()
