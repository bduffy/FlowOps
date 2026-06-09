#!/usr/bin/env bash
# Week-0 spike — AWS orphan detection. Throwaway.
#
# Find S3 buckets that exist in the account but are ABSENT from tofu state, by tag.
# We ask AWS directly (not tofu state) so lost/corrupt state cannot hide a resource.
#
# Usage: AWS_PROFILE=... ./detect_orphans.sh <run_id>
#   (run with the SAME assumed-role context as the apply, e.g. via aws sts assume-role
#    or an AWS_PROFILE that assumes the sandbox role)
set -euo pipefail

RUN_ID="${1:?usage: detect_orphans.sh <run_id>}"
echo "== AWS orphan scan for run=${RUN_ID} =="

# 1. State view.
in_state="$(tofu state list 2>/dev/null | grep -c 'aws_s3_bucket\.' || true)"
echo "tofu state: ${in_state} bucket(s) tracked"

# 2. Cloud view: S3 has no server-side tag filter for ListBuckets, so list all and
#    check each bucket's tag set for our run-id. (Fine at spike scale.)
orphans=()
while read -r bkt; do
  [ -z "$bkt" ] && continue
  tags="$(aws s3api get-bucket-tagging --bucket "$bkt" \
            --query "TagSet[?Key=='flowops-spike-run'].Value | [0]" \
            --output text 2>/dev/null || true)"
  if [ "$tags" = "$RUN_ID" ]; then
    # Belongs to this run. Is tofu aware of it?
    if ! tofu state list 2>/dev/null | xargs -I{} tofu state show {} 2>/dev/null \
         | grep -q "bucket *= *\"${bkt}\""; then
      orphans+=("$bkt")
    fi
  fi
done < <(aws s3api list-buckets --query "Buckets[].Name" --output text 2>/dev/null | tr '\t' '\n')

echo "cloud:       $(( ${#orphans[@]} )) untracked bucket(s) tagged run=${RUN_ID}"

if [ "${#orphans[@]}" -eq 0 ]; then
  echo "RESULT: no orphans (cloud and state agree)"
  exit 0
fi

echo "RESULT: ${#orphans[@]} ORPHAN(S) detected (in account, not in tofu state):"
printf '  - s3://%s\n' "${orphans[@]}"
echo ""
echo "To reclaim:"
for o in "${orphans[@]}"; do echo "  aws s3 rb s3://${o} --force"; done
exit 3
