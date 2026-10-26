#!/bin/bash
# Used by .github/workflows/portal-infra.yml after `terraform plan -out=<plan>`.
#
# Writes the plan to the job summary and fails if it would destroy or replace
# any resource, unless ALLOW_REPLACE=true. Replacing aws_instance.host wipes
# the portal (its SQLite database lives on the root volume).
#
# Usage: check-plan.sh <planfile>     (run from the Terraform directory)
set -euo pipefail

PLAN="${1:?usage: check-plan.sh <planfile>}"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"

terraform show -json "$PLAN" > plan.json
DESTRUCTIVE=$(jq -r '
  .resource_changes[]?
  | select(.change.actions | index("delete"))
  | "\(.address) (\(.change.actions | join("/")))"' plan.json)
CHANGES=$(jq '[.resource_changes[]? | select(.change.actions != ["no-op"] and .change.actions != ["read"])] | length' plan.json)

{
  echo "### Terraform plan: $CHANGES resource change(s)"
  echo '<details><summary>Plan</summary>'
  echo
  echo '```'
  terraform show -no-color "$PLAN"
  echo '```'
  echo '</details>'
} >> "$SUMMARY"

if [ -n "$DESTRUCTIVE" ]; then
  {
    echo
    echo "**Destroys or replaces:**"
    echo '```'
    echo "$DESTRUCTIVE"
    echo '```'
  } >> "$SUMMARY"
  if [ "${ALLOW_REPLACE:-false}" != "true" ]; then
    while read -r line; do echo "::error::Plan destroys or replaces $line"; done <<< "$DESTRUCTIVE"
    echo "Re-run Portal Infrastructure by hand with action=apply and allow_replace=true if this is intended." >&2
    exit 1
  fi
  echo "::warning::allow_replace=true - applying a plan that destroys or replaces resources"
fi
