# Week-0 spike — AWS. Throwaway. Proves scoped-role isolation + provision/destroy/orphan.
#
#  flow:
#    assume scoped role (no static keys)  ->  create sandbox BUCKET (tagged run_id)
#                                               |
#                                   [inject_failure] -> a step that always fails,
#                                   so apply errors AFTER the bucket exists (phase 4)

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.0" }
    null   = { source = "hashicorp/null", version = "~> 3.0" }
  }
}

provider "aws" {
  region = var.region
  # Isolation: assume a scoped role into the sandbox account. No long-lived keys.
  # SR4: the role should be narrowly scoped + use a tight trust policy (ExternalId,
  # exact principal). The spike just demonstrates the assume-role path.
  assume_role {
    role_arn     = var.assume_role_arn
    session_name = "flowops-spike-${var.run_id}"
    external_id  = var.external_id == "" ? null : var.external_id
  }
}

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  common_tags = {
    "flowops-spike-run" = var.run_id
    "flowops-spike"     = "true"
  }
}

# --- The "sandbox" payload: one tiny, billable, tagged resource --------------
resource "aws_s3_bucket" "sandbox" {
  bucket        = "flowops-sbx-${var.run_id}-${random_id.suffix.hex}"
  force_destroy = true
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "sandbox" {
  bucket                  = aws_s3_bucket.sandbox.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- Phase 4 lever: force a mid-apply failure AFTER the bucket exists --------
resource "null_resource" "inject_failure" {
  count      = var.inject_failure ? 1 : 0
  depends_on = [aws_s3_bucket.sandbox]
  provisioner "local-exec" {
    command = "echo 'flowops-spike: injecting deliberate failure after bucket creation' >&2; exit 1"
  }
}

output "sandbox_bucket" { value = aws_s3_bucket.sandbox.bucket }
output "run_id" { value = var.run_id }
