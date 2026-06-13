"""Generate a synthetic 'swamp': a client master and ~40 messy documents
dumped into raw buckets with meaningless keys, like a real legacy estate."""
import csv, io, random, datetime as dt
from common import load_ontology, s3, put_json

random.seed(7)
TODAY = dt.date(2026, 6, 12)

CLIENTS = [
    # id, segment, legal_name, jurisdiction, group, risk
    ("C1001", "CIB", "Meridian Holdings Pte Ltd",        "SG", "G-MERIDIAN", "high"),
    ("C1002", "CIB", "Meridian Trading (Asia) Pte Ltd",  "SG", "G-MERIDIAN", "high"),
    ("C1003", "CIB", "Meridian Infra India Pvt Ltd",     "IN", "G-MERIDIAN", "medium"),
    ("C1004", "CIB", "Eastgate Commodities Pte Ltd",     "SG", "G-EASTGATE", "medium"),
    ("C1005", "CIB", "Eastgate Shipping Pte Ltd",        "SG", "G-EASTGATE", "low"),
    ("C1006", "CIB", "Sundaram Textile Mills Pvt Ltd",   "IN", "G-SUNDARAM", "medium"),
    ("W2001", "WRB", "Tan Wei Ming",                     "SG", "",           "low"),
    ("W2002", "WRB", "Priya Raghunathan",                "IN", "",           "medium"),
    ("W2003", "WRB", "Daniel Koh Jun Jie",               "SG", "",           "high"),
    ("W2004", "WRB", "Aarav Mehta",                      "IN", "",           "low"),
]

ALIASES = {  # how names actually appear in old scans
    "C1001": ["Meridian Holdings Pte. Ltd.", "MERIDIAN HOLDINGS PTE LTD", "Meridian Holdings"],
    "C1002": ["Meridian Trading Asia Pte Ltd", "Meridian Trading (Asia)"],
    "C1003": ["Meridian Infra (India) Private Limited", "Meridian Infra India"],
    "C1004": ["Eastgate Commodities Pte. Ltd.", "EASTGATE COMMODITIES"],
    "C1005": ["Eastgate Shipping Pte Ltd"],
    "C1006": ["Sundaram Textile Mills Private Ltd", "M/s Sundaram Textile Mills"],
    "W2001": ["TAN WEI MING", "Tan Wei Ming"],
    "W2002": ["Priya Raghunathan", "RAGHUNATHAN, PRIYA"],
    "W2003": ["KOH JUN JIE DANIEL", "Daniel Koh"],
    "W2004": ["Aarav Mehta", "MEHTA AARAV"],
}

def ocr_noise(text, rate=0.012):
    subs = {"O": "0", "l": "1", "S": "5", "e": "c", "m": "rn"}
    out = []
    for ch in text:
        out.append(subs.get(ch, ch) if random.random() < rate and ch in subs else ch)
    return "".join(out)

def d(y_ago_min, y_ago_max):
    days = random.randint(int(y_ago_min * 365), int(y_ago_max * 365))
    return TODAY - dt.timedelta(days=days)

def doc_identity(name, expired=None):
    issue = d(3, 9)
    if expired is True:  exp = TODAY - dt.timedelta(days=random.randint(30, 400))
    elif expired == "soon": exp = TODAY + dt.timedelta(days=random.randint(20, 80))
    else: exp = TODAY + dt.timedelta(days=random.randint(200, 1500))
    return (f"REPUBLIC OF SINGAPORE / REPUBLIK SINGAPURA\nPASSPORT\n"
            f"Name: {name}\nPassport No: K{random.randint(1000000,9999999)}A\n"
            f"Date of Issue: {issue}\nDate of Expiry: {exp}\n"), issue

def doc_incorp(name):
    issue = d(6, 18)
    return (f"ACCOUNTING AND CORPORATE REGULATORY AUTHORITY\n"
            f"CERTIFICATE CONFIRMING INCORPORATION OF COMPANY\n"
            f"This is to certify that {name} was incorporated under the Companies Act\n"
            f"Registration No: {random.randint(199000000,202399999)}{random.choice('KMNZ')}\n"
            f"Date of Incorporation: {issue}\n"), issue

def doc_ubo(name, stale=False):
    issue = d(2.5, 4) if stale else d(0.2, 1.5)
    pct = random.choice([55, 60, 75, 100])
    return (f"DECLARATION OF ULTIMATE BENEFICIAL OWNERSHIP\nEntity: {name}\n"
            f"Declared UBO: {random.choice(['H. Lindqvist','R. Subramaniam','C. W. Ong','A. Petrova'])}"
            f" holding {pct}% via intermediate entities\nDeclaration Date: {issue}\n"), issue

def doc_financials(name, stale=False):
    issue = d(2.2, 3.5) if stale else d(0.3, 1.2)
    return (f"AUDITED FINANCIAL STATEMENTS\nFor: {name}\nFinancial Year End: {issue}\n"
            f"Auditor: {random.choice(['KPMG LLP','EY LLP','Deloitte & Touche'])}\n"
            f"Total Assets: {random.choice(['USD 84.2m','SGD 412.7m','USD 1.03bn','INR 6.4bn'])}\n"), issue

def doc_facility(name):
    issue = d(1, 7)
    return (f"FACILITY AGREEMENT\nBorrower: {name}\nLender: Example Bank\n"
            f"Facility Amount: {random.choice(['USD 50,000,000','SGD 120,000,000','USD 250,000,000'])}\n"
            f"Governing Law: {random.choice(['Singapore','English'])} law\nSigning Date: {issue}\n"), issue

def doc_address(name):
    issue = d(0.1, 2.5)
    return (f"UTILITY STATEMENT\nAccount Holder: {name}\n"
            f"Service Address: Blk {random.randint(10,900)} {random.choice(['Tampines','Bedok','Andheri East','Jurong'])} "
            f"Ave {random.randint(1,9)}\nStatement Date: {issue}\n"), issue

def doc_junk():
    return ("INVOICE\nFrom: Apex Office Supplies\nTo: Facilities Dept\n"
            "Item: Toner cartridges x 24\nAmount: SGD 1,420.00\n"), d(1, 8)

MAKERS = {"identity": doc_identity, "incorporation": doc_incorp, "ownership_control": doc_ubo,
          "financials": doc_financials, "facility_docs": doc_facility, "address_proof": doc_address}

def plan_docs():
    plan = []  # (client_id|None, kind, kwargs)
    for cid, seg, name, jur, grp, risk in CLIENTS:
        if seg == "CIB":
            plan += [(cid, "identity", {}), (cid, "incorporation", {}),
                     (cid, "facility_docs", {}), (cid, "correspondencefiller", {})]
            plan.append((cid, "ownership_control", {"stale": cid in ("C1004",)}))
            if cid != "C1005":  # C1005 missing financials entirely -> gap
                plan.append((cid, "financials", {"stale": cid in ("C1006",)}))
        else:
            exp = True if cid == "W2003" else ("soon" if cid == "W2002" else None)
            plan.append((cid, "identity", {"expired": exp}))
            if cid != "W2004":  # W2004 missing address proof -> gap (low risk: not required)
                plan.append((cid, "address_proof", {}))
    plan += [(None, "junk", {}), (None, "junk", {})]
    return plan

def main():
    ont, client = load_ontology(), s3()
    # buckets per jurisdiction (sovereignty topology)
    for jur in ont["jurisdictions"]:
        for tpl in ont["buckets"].values():
            try: client.create_bucket(Bucket=tpl.format(jur=jur.lower()))
            except client.exceptions.BucketAlreadyOwnedByYou: pass

    with open("data_client_master.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["id","segment","legal_name","jurisdiction","group","risk"])
        w.writerows(CLIENTS)

    by_id = {c[0]: c for c in CLIENTS}
    n = 0
    for cid, kind, kw in plan_docs():
        n += 1
        raw_name = random.choice(["scan", "IMG", "doc", "fax", "batch"]) + f"_{random.randint(1000,99999)}.txt"
        if kind == "junk":
            body, issue = doc_junk(); jur = random.choice(["SG", "IN"])
        elif kind == "correspondencefiller":
            _, seg, name, jur, _, _ = by_id[cid]; issue = d(0.5, 6)
            body = f"Re: account servicing\nDear Sir, we refer to {random.choice(ALIASES[cid])}...\nDate: {issue}\n"
        else:
            _, seg, name, jur, _, _ = by_id[cid]
            body, issue = MAKERS[kind](random.choice(ALIASES[cid]), **kw)
        bucket = ont["buckets"]["raw"].format(jur=jur.lower())
        client.put_object(Bucket=bucket, Key=f"legacy/{issue.year}/{raw_name}",
                          Body=ocr_noise(body).encode())
    print(f"swamp created: {n} documents across raw buckets")

if __name__ == "__main__":
    main()
