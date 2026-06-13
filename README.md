# pKYC POC — Intelligent Structure Layer on an Object Store

Proves the end-to-end loop on synthetic data:

```
raw swamp (messy keys, OCR noise)
   → classify + extract            (Claude API, heuristic fallback)
   → entity-resolve                (vs client master, confidence-gated)
   → materialize clean zone        (sovereignty-shaped S3 keys + manifests + lineage)
   → client file state             (holdings vs requirements matrix, validity tracked)
   → pKYC triggers                 (expiry/staleness + external event materiality diff)
   → agent task queue              (micro-refresh packs, drafted outreach, human gates)
   → ops dashboard                 (out/dashboard.html — screenshot this)
```

## Run & verify locally (no infra, no keys needed)
```bash
python3 -m venv .venv && source .venv/bin/activate   # optional but tidy
pip install -r requirements.txt
./run_demo.sh        # local S3 server + full pipeline + verification checks
```
Expect the final lines: `VERIFY OK — all checks passed across 44 docs / 10 client files / 6 tasks`.
Then open `out/coo_briefing.html` (executive view) and `out/dashboard.html` (technical view).

`src/checks.py` asserts the claims the demo makes — sovereignty isolation
(no client's docs outside their booking jurisdiction), quarantine integrity,
confidence gating vs ontology thresholds, manifest consistency, and pKYC state
logic. Re-run it any time; it exits non-zero on any violation.

**Try the live-demo moment**: edit `config/ontology.yaml` (e.g. add `financials`
to `requirements.CIB.low`), re-run `./run_demo.sh`, and watch a green client
flip to amber with a new agent task. Policy as configuration, verified.

Windows note: run the four python steps from run_demo.sh manually, or use WSL.

## Run against MinIO on GCP (the real demo)
1. Create a small GCE VM (e2-standard-2 is plenty). Open port 9000/9001 to your IP only.
2. `docker compose up -d` (uses docker-compose.yml here) — MinIO console on :9001.
3. Point the pipeline at it and use real model extraction:
```bash
export S3_ENDPOINT=http://<vm-ip>:9000
export S3_KEY=minioadmin S3_SECRET=minioadmin   # change in compose for anything non-throwaway
export ANTHROPIC_API_KEY=sk-ant-...             # enables Claude extraction path
./run_demo.sh
```
4. Screenshots for the deck: the MinIO console showing `poc-sg-clean` / `poc-in-clean`
   bucket trees (sovereignty topology is *visible* in the storage browser), plus
   `out/dashboard.html` (estate stats, client file state board, agent task queue).

Note: GCS also exposes an S3-interoperable XML API with HMAC keys if you'd rather
not run MinIO, but MinIO is the more faithful stand-in for an on-prem bank estate.

## What each file is
- `config/ontology.yaml` — the whole point: layout, retention, requirements matrix,
  resolution thresholds as *configuration*. Change it; the estate reshapes.
- `src/synth.py` — builds the swamp: 44 docs, junk filenames, OCR noise, name variants,
  expired passports, stale UBO/financials, two unresolvable junk invoices.
- `src/pipeline.py` — extraction (Claude or heuristic), entity resolution with
  auto-accept / human-review / quarantine bands, clean-zone materialization,
  per-entity holdings manifests, client-group pointer manifests, lineage records.
- `src/pkyc.py` — the state engine: file state vs requirements matrix, validity
  triggers, event materiality diff (ownership change → micro-refresh of one doc;
  adverse media on non-low-risk → escalate), agent task queue with human gates.
- `src/dashboard.py` — renders `out/dashboard.html` from the run outputs.

## Talking points the POC demonstrates
1. **Layout is governance**: jurisdiction = bucket, retention/ACLs attach to prefixes.
2. **Confidence-gated placement**: nothing enters the clean zone below threshold;
   wrong-prefix misfiles are designed against, not hoped against.
3. **pKYC is a state problem**: the diff engine only works because current holdings
   are trustworthy — this is the thing Fenergo assumes and never builds.
4. **Agents execute, humans decide**: every task carries its evidence, scope, and
   an explicit human gate — the framing that survives model-risk review.

## Deliberate POC shortcuts (say these out loud in the demo)
Synthetic text stands in for OCR'd scans (production: OCR + layout models in front);
resolution is fuzzy-match (production: client-master MDM integration); events are a
stubbed feed (production: registry/screening/media adapters); the agent queue emits
JSON (production: feeds your in-house workflow tool's API).
