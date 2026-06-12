# Week-0 spike — AWS variables. Throwaway.

variable "run_id" {
  description = "Unique tag applied to every resource for orphan detection + cleanup."
  type        = string
}

variable "region" {
  description = "AWS region for the sandbox bucket."
  type        = string
  default     = "us-east-1"
}

# Isolation via role-assumption into a pre-existing sandbox account (no static keys).
# This is the runnable stand-in for account-per-sandbox; account VENDING (AWS
# Organizations) is documented in README but not run by the spike (slow/quota-limited).
variable "assume_role_arn" {
  description = "ARN of the scoped role to assume into the sandbox account."
  type        = string
}

variable "external_id" {
  description = "Optional ExternalId for the assume-role trust (defense in depth)."
  type        = string
  default     = ""
}

# When true, a guaranteed-to-fail step runs AFTER the bucket is created (phase 4).
variable "inject_failure" {
  description = "Inject a mid-apply failure after the sandbox resource is created."
  type        = bool
  default     = false
}
