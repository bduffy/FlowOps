# Week-0 spike — GCP. Throwaway. Proves project-per-sandbox + provision/destroy/orphan.
#
#  flow:
#    [optional] create sandbox PROJECT  ->  create sandbox BUCKET (labeled run_id)
#                                              |
#                                  [inject_failure] -> a step that always fails,
#                                  so apply errors AFTER the bucket exists (phase 4)

terraform {
  required_version = ">= 1.6"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.0" }
    null   = { source = "hashicorp/null", version = "~> 3.0" }
  }
}

provider "google" {
  # Credentials come from the ambient `gcloud` / ADC environment — never stored here.
  # Quota/host project for API calls; resources land in the sandbox project below.
}

resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  # Project-per-sandbox: create one, or use an existing project to keep the run cheap.
  sandbox_project_id = var.create_project ? google_project.sandbox[0].project_id : var.existing_project
  common_labels = {
    "flowops-spike-run" = var.run_id
    "flowops-spike"     = "true"
  }
}

# --- The isolation boundary: a project per sandbox ---------------------------
resource "google_project" "sandbox" {
  count           = var.create_project ? 1 : 0
  name            = "flowops-sbx-${var.run_id}"
  project_id      = "flowops-sbx-${var.run_id}-${random_id.suffix.hex}"
  org_id          = var.folder_id == "" ? var.org_id : null
  folder_id       = var.folder_id == "" ? null : var.folder_id
  billing_account = var.billing_account
  labels          = local.common_labels
  # Teardown = delete the project. In production this is the orphan-resistant path.
  deletion_policy = "DELETE"
}

# --- The "sandbox" payload: one tiny, billable, labeled resource -------------
resource "google_storage_bucket" "sandbox" {
  name                        = "flowops-sbx-${var.run_id}-${random_id.suffix.hex}"
  project                     = local.sandbox_project_id
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true
  labels                      = local.common_labels
}

# --- Phase 4 lever: force a mid-apply failure AFTER the bucket exists --------
# Proves apply can die partway and leave a real, billable resource behind.
resource "null_resource" "inject_failure" {
  count      = var.inject_failure ? 1 : 0
  depends_on = [google_storage_bucket.sandbox]
  provisioner "local-exec" {
    command = "echo 'flowops-spike: injecting deliberate failure after bucket creation' >&2; exit 1"
  }
}

output "sandbox_project_id" { value = local.sandbox_project_id }
output "sandbox_bucket" { value = google_storage_bucket.sandbox.name }
output "run_id" { value = var.run_id }
