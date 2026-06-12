#!/usr/bin/env bash
# Week-0 spike orchestrator. Throwaway. Walks the 5 phases per cloud, prints PASS/FAIL.
#
# Usage:
#   ./run.sh gcp        # GCP only   (env: TF_VAR_create_project, TF_VAR_org_id,
#                       #             TF_VAR_billing_account OR TF_VAR_existing_project)
#   ./run.sh aws        # AWS only   (env: TF_VAR_assume_role_arn [, TF_VAR_external_id])
#   ./run.sh all        # both, sequentially
#
# Reads cloud-specific inputs from TF_VAR_* env vars (tofu picks them up automatically).
# Never stores credentials. Tags every resource flowops-spike-run=<run-id>.
set -uo pipefail

CLOUD="${1:?usage: run.sh <gcp|aws|all>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
# run_id: short, unique-per-run, lowercase (valid in bucket names + labels).
RUN_ID="r$(date +%s | tail -c 7)"
PASS=0; FAIL=0

say()  { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$*"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; FAIL=$((FAIL+1)); }
note() { printf '  ·    %s\n' "$*"; }

run_cloud() {
  # NB: separate `local` statements — `local a=$1 b=$a` expands $a before a is set
  # (local's args are expanded before assignment), which trips `set -u`.
  local cloud="$1"
  local dir="$HERE/$cloud"
  say "CLOUD: $cloud   run_id=$RUN_ID"
  cd "$dir" || { bad "$cloud dir missing"; return; }
  export TF_VAR_run_id="$RUN_ID"
  local t0 t1

  tofu init -input=false -no-color >/dev/null 2>&1 || { bad "$cloud tofu init failed"; return; }

  # ---- Phases 1-3: isolated provision -> clean apply -> clean destroy ----------
  say "$cloud · phases 1-3: provision / apply / destroy"
  t0=$(date +%s)
  if tofu apply -auto-approve -input=false -no-color >/tmp/spike-$cloud-apply.log 2>&1; then
    t1=$(date +%s); ok "apply succeeded in $((t1-t0))s ($(tofu output -raw sandbox_bucket 2>/dev/null))"
  else
    bad "apply failed — see /tmp/spike-$cloud-apply.log"; return
  fi
  t0=$(date +%s)
  if tofu destroy -auto-approve -input=false -no-color >/tmp/spike-$cloud-destroy.log 2>&1; then
    t1=$(date +%s)
    [ "$(tofu state list 2>/dev/null | wc -l | tr -d ' ')" = "0" ] \
      && ok "destroy clean in $((t1-t0))s (state empty)" \
      || bad "destroy left resources in state"
  else
    bad "destroy failed — see /tmp/spike-$cloud-destroy.log"
  fi

  # ---- Phase 4: failed-apply accounting ---------------------------------------
  say "$cloud · phase 4: deliberate mid-apply failure"
  if TF_VAR_inject_failure=true tofu apply -auto-approve -input=false -no-color \
       >/tmp/spike-$cloud-fail.log 2>&1; then
    bad "injected-failure apply unexpectedly SUCCEEDED"
  else
    note "apply failed as expected (partial resource created)"
    # the bucket exists but the run errored; clean it up via destroy of what's in state
    tofu destroy -auto-approve -input=false -no-color >/dev/null 2>&1 || true
    ok "partial resource accounted for + cleaned"
  fi

  # ---- Phase 5: orphan detection independent of tofu state --------------------
  say "$cloud · phase 5: orphan detection (state lost)"
  TF_VAR_inject_failure=false tofu apply -auto-approve -input=false -no-color \
      >/tmp/spike-$cloud-orphan-apply.log 2>&1 || { bad "orphan-setup apply failed"; return; }
  local bucket addr proj=""
  bucket="$(tofu output -raw sandbox_bucket 2>/dev/null)"
  # GCS buckets live in a project; the detector must be told which one (gcloud's
  # default project is not the sandbox project). Capture it BEFORE state rm.
  [ "$cloud" = gcp ] && proj="$(tofu output -raw sandbox_project_id 2>/dev/null || true)"
  addr="$([ "$cloud" = gcp ] && echo google_storage_bucket.sandbox || echo aws_s3_bucket.sandbox)"
  tofu state rm "$addr" >/dev/null 2>&1   # simulate lost/corrupt state -> bucket is now an orphan
  note "removed $bucket from tofu state (now an orphan in the cloud)"

  if ./detect_orphans.sh "$RUN_ID" "$proj" >/tmp/spike-$cloud-detect.log 2>&1; then
    bad "orphan detector reported NO orphans (it should have found $bucket)"
    note "$(tail -1 /tmp/spike-$cloud-detect.log)"
  elif grep -q "$bucket" /tmp/spike-$cloud-detect.log; then
    ok "orphan detector found the untracked resource"
  else
    bad "orphan detector could not confirm the orphan — reason below"
    grep -E 'ERROR|WARN|active account|RESULT' /tmp/spike-$cloud-detect.log | sed 's/^/      /' | head -4
  fi

  # cleanup the orphan via cloud CLI (tofu no longer tracks it)
  if [ "$cloud" = gcp ]; then gcloud storage rm --recursive "gs://$bucket" >/dev/null 2>&1 || true
  else aws s3 rb "s3://$bucket" --force >/dev/null 2>&1 || true; fi
  # destroy anything still tracked (e.g. a created sandbox project in GCP create mode)
  tofu destroy -auto-approve -input=false -no-color >/dev/null 2>&1 || true
  note "orphan reclaimed"
  rm -f terraform.tfstate terraform.tfstate.backup 2>/dev/null || true
}

case "$CLOUD" in
  gcp) run_cloud gcp ;;
  aws) run_cloud aws ;;
  all) run_cloud gcp; run_cloud aws ;;
  *)   echo "unknown cloud: $CLOUD (use gcp|aws|all)"; exit 2 ;;
esac

say "SUMMARY   PASS=$PASS  FAIL=$FAIL"
echo "Record timings + friction in RESULTS.md, then decide the first-class cloud."
[ "$FAIL" -eq 0 ]
