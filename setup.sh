#!/usr/bin/env bash
# One-time setup for the tech-report PPTX agent (opencode).
# Fetches ppt-master (MIT, https://github.com/hugohe3/ppt-master) UNMODIFIED into vendor/ppt-master
# and links it as an opencode skill. ppt-master has an integrity guard: never edit its files.
set -euo pipefail
cd "$(dirname "$0")"
PPT_MASTER_REF="${PPT_MASTER_REF:-main}"   # pin to a tag/commit for reproducible builds, e.g. PPT_MASTER_REF=v6.8.0
python3 -m pip install -q python-pptx lxml pillow
if [ ! -d vendor/ppt-master/.git ]; then
  mkdir -p vendor
  git clone --depth 1 --branch "$PPT_MASTER_REF" https://github.com/hugohe3/ppt-master.git vendor/ppt-master
fi
python3 -m pip install -q -r vendor/ppt-master/skills/ppt-master/requirements.txt || echo "WARN: ppt-master requirements not fully installed (route B may be limited)"
ln -sfn ../../vendor/ppt-master/skills/ppt-master .opencode/skills/ppt-master
python3 vendor/ppt-master/skills/ppt-master/scripts/attribution_guard.py && echo "ppt-master integrity guard: OK"
# Visual self-check needs a renderer: PPTX -> PDF (LibreOffice) -> PNG (poppler). Without them the agent cannot LOOK at its slides.
for t in soffice pdftoppm; do
  command -v "$t" >/dev/null 2>&1 || echo "WARN: '$t' not found — install LibreOffice and poppler (macOS: brew install --cask libreoffice && brew install poppler; Ubuntu: sudo apt install libreoffice poppler-utils) so deck_preview / deck_compare / golden checks work"
done
echo "Ready. Start: opencode  (then select the 'tech-report-pptx' agent with Tab)"
