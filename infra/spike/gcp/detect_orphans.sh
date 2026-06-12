#!/usr/bin/env bash
# Week-0 spike — GCP orphan detection. Throwaway.
#
# Find buckets that exist in the CLOUD but are ABSENT from tofu state (lost/corrupt
# state, or a half-failed apply). We ask the cloud directly — not tofu state.
#
# GCP specifics learned the hard way:
#   - buckets live in a PROJECT; scope the scan to the sandbox project (arg 2), not
#     gcloud's default project.
#   - gcloud's --filter/--format dotted paths treat `labels.flowops-spike-run` as
#     subtraction (hyphens!). So we read each bucket's labels blob and grep the run-id
#     in the shell, never via a gcloud filter expression.
#   - no `mapfile` (bash 4+) — keep it bash 3.2 friendly.
#
# Usage: ./detect_orphans.sh <run_id> [project_id]
set -euo pipefail

RUN_ID="${1:?usage: detect_orphans.sh <run_id> [project_id]}"
PROJECT="${2:-}"

echo "== GCP orphan scan for run=${RUN_ID} project=${PROJECT:-<gcloud default>} =="
[ -z "$PROJECT" ] && echo "  WARN: no project given — scanning gcloud's default project only"

proj_flag=()
[ -n "$PROJECT" ] && proj_flag=(--project "$PROJECT")

# 1. State view.
in_state="$(tofu state list 2>/dev/null | grep -c 'google_storage_bucket' || true)"
echo "tofu state: ${in_state} bucket(s) tracked"

# 2. Cloud view: list buckets in the project, check each one's labels for our run-id
#    (in-shell, hyphen-safe). In cloud + not in tofu state = ORPHAN.
orphans=()
while read -r name; do
  [ -z "$name" ] && continue
  labels="$(gcloud storage buckets describe "gs://${name}" \
              "${proj_flag[@]}" --format='value(labels)' 2>/dev/null || true)"
  printf '%s' "$labels" | grep -q -- "$RUN_ID" || continue   # not ours
  if ! tofu state list 2>/dev/null | xargs -I{} tofu state show {} 2>/dev/null \
       | grep -q "name *= *\"${name}\""; then
    orphans+=("$name")
  fi
done < <(gcloud storage buckets list "${proj_flag[@]}" --format="value(name)" 2>/dev/null || true)

echo "cloud:       ${#orphans[@]} untracked bucket(s) labeled run=${RUN_ID}"

if [ "${#orphans[@]}" -eq 0 ]; then
  echo "RESULT: no orphans (cloud and state agree)"
  exit 0
fi

echo "RESULT: ${#orphans[@]} ORPHAN(S) detected (in cloud, not in tofu state):"
printf '  - gs://%s\n' "${orphans[@]}"
echo ""
echo "To reclaim:"
for o in "${orphans[@]}"; do echo "  gcloud storage rm --recursive gs://${o}"; done
exit 3
