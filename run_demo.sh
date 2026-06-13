#!/usr/bin/env bash
# End-to-end demo. Against MinIO: export S3_ENDPOINT/S3_KEY/S3_SECRET first.
# Optional: export ANTHROPIC_API_KEY to use Claude for extraction.
set -e
cd "$(dirname "$0")"
if [ -z "$S3_ENDPOINT" ]; then
  echo "[demo] no S3_ENDPOINT set — starting local moto S3 on :9000"
  python3 -m moto.server -p 9000 >/tmp/moto.log 2>&1 &
  MOTO_PID=$!; sleep 2; trap "kill $MOTO_PID" EXIT
fi
python3 src/synth.py
python3 src/pipeline.py
python3 src/pkyc.py
python3 src/dashboard.py
python3 src/coo_view.py
python3 src/checks.py
echo "[demo] open out/dashboard.html"
