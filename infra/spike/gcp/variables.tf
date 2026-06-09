# Week-0 spike — GCP variables. Throwaway.

variable "run_id" {
  description = "Unique tag applied to every resource for orphan detection + cleanup."
  type        = string
}

variable "region" {
  description = "GCP region for the sandbox bucket."
  type        = string
  default     = "us-east1"
}

# --- Project-per-sandbox (the real isolation model) ---------------------------
# When create_project = true, the spike creates a brand-new GCP project to act as
# the isolated sandbox, then provisions inside it. This proves project-per-sandbox.
# Requires org_id (or folder_id) + billing_account.
variable "create_project" {
  description = "If true, create a new project as the sandbox (project-per-sandbox)."
  type        = bool
  default     = false
}

variable "org_id" {
  description = "GCP Organization ID (required when create_project = true, unless folder_id set)."
  type        = string
  default     = ""
}

variable "folder_id" {
  description = "GCP Folder ID to create the sandbox project under (optional)."
  type        = string
  default     = ""
}

variable "billing_account" {
  description = "Billing account ID to link the sandbox project (required when create_project = true)."
  type        = string
  default     = ""
}

# When create_project = false, provision into this existing project (cheap to run).
variable "existing_project" {
  description = "Existing project ID to provision the sandbox bucket into (when create_project = false)."
  type        = string
  default     = ""
}

# --- Orphan-detection lever ---------------------------------------------------
# When true, a guaranteed-to-fail step runs AFTER the bucket is created, so apply
# fails mid-way leaving a partial resource (phase 4: failed-apply accounting).
variable "inject_failure" {
  description = "Inject a mid-apply failure after the sandbox resource is created."
  type        = bool
  default     = false
}
