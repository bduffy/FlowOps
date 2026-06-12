#!/usr/bin/env bash
# Week-0 spike — GCP orphan detection. Throwaway.
#
# The hard problem: find resources that exist in the CLOUD but are ABSENT from tofu
# state (lost/corrupt state, or a half-failed apply). We do NOT trust tofu state to
# tell us what exists — we ask the cloud directly, by run-label, and diff.
#
# Usage: ./detect_orphans.sh <run_id> [project_id]
set -euo pipefail

RUN_ID="${1:?usage: detect_orphans.sh <run_id> [project_id]}"
PROJECT="${2:-}"

echo "== GCP orphan scan for run=${RUN_ID} =="

# 1. What does tofu THINK exists?
in_state="$(tofu state list 2>/dev/null | grep -c 'google_storage_bucket' || true)"
echo "tofu state: ${in_state} bucket(s) tracked"

# 2. What ACTUALLY exists in the cloud, by label? (source of truth)
#    Scope to the sandbox project if given, else search the ambient project.
project_flag=()
[ -n "$PROJECT" ] && project_flag=(--project "$PROJECT")

mapfile -t cloud_buckets < <(
  gcloud storage buckets list "${project_flag[@]}" \
    --filter="labels.flowops-spike-run=${RUN_ID}" \
    --format="value(name)" 2>/dev/null || true
)
echo "cloud:       ${#cloud_buckets[@]} bucket(s) labeled run=${RUN_ID}"

# 3. Diff: anything in the cloud that tofu state does not know about = ORPHAN.
orphans=()
for b in "${cloud_buckets[@]}"; do
  name="${b#gs://}"; name="${name%/}"
  if ! tofu state list 2>/dev/null | xargs -I{} tofu state show {} 2>/dev/null \
       | grep -q "name *= *\"${name}\""; then
    orphans+=("$name")
  fi
done

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
