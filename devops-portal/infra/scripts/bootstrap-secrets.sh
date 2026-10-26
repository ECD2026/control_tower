#!/bin/bash
# One-time (idempotent) secret setup for the hosted portal. Run by an operator
# from a machine with the AWS CLI and GitHub CLI logged in.
#
#   ./bootstrap-secrets.sh [region] [github-repo]
#
# Writes SecureString parameters under /devops-portal/ that host-deploy.sh
# turns into the portal's .env, and stores the shared workflow key as the
# PORTAL_WORKFLOW_KEY GitHub Actions secret. Existing values are kept, so
# re-running never invalidates stored credentials or sessions.
#
# GITHUB_TOKEN: export PORTAL_GITHUB_TOKEN with a fine-grained PAT limited to
# the repo (Actions: read & write, Contents: read). Without it the script
# falls back to `gh auth token` - fine for a demo, too broad for production.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # keep /devops-portal paths intact in Git Bash

REGION="${1:-ap-south-1}"
REPO="${2:-ECD2026/control_tower}"
PREFIX=/devops-portal

exists() {
  aws ssm get-parameter --region "$REGION" --name "$PREFIX/$1" >/dev/null 2>&1
}

put() {  # put <name> <value> <type> <description>
  aws ssm put-parameter --region "$REGION" --name "$PREFIX/$1" --value "$2" \
    --type "$3" --description "$4" --overwrite >/dev/null
  aws ssm add-tags-to-resource --region "$REGION" --resource-type Parameter \
    --resource-id "$PREFIX/$1" \
    --tags Key=Project,Value=devops-portal Key=Component,Value=portal-host >/dev/null
  echo "  set $PREFIX/$1"
}

put_once() {  # only creates; never rotates an existing secret
  if exists "$1"; then echo "  kept $PREFIX/$1"; else put "$@"; fi
}

fernet() { python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"; }
token()  { python -c "import secrets;print(secrets.token_urlsafe(48))"; }

echo "==> SSM parameters in $REGION"
put_once encryption_key "$(fernet)" SecureString "Fernet key encrypting secrets at rest in the portal DB"
put_once jwt_secret "$(token)" SecureString "HS256 secret for portal session tokens"
put_once workflow_key "$(fernet)" SecureString "Fernet key shared with GitHub Actions (PORTAL_WORKFLOW_KEY)"
put_once grafana_admin_password "$(token)" SecureString "Grafana admin password"

GH_TOKEN_VALUE="${PORTAL_GITHUB_TOKEN:-$(gh auth token)}"
put github_token "$GH_TOKEN_VALUE" SecureString "Token the portal uses to dispatch portal-deploy.yml"
put_once runner_mode "${PORTAL_RUNNER_MODE:-github_actions}" String "local | github_actions"
put_once allow_signup "true" String "PORTAL_ALLOW_SIGNUP: true | false | first"

echo "==> GitHub secret PORTAL_WORKFLOW_KEY on $REPO"
aws ssm get-parameter --region "$REGION" --with-decryption --name "$PREFIX/workflow_key" \
  --query Parameter.Value --output text | gh secret set PORTAL_WORKFLOW_KEY --repo "$REPO"

echo "Done. Redeploy the host (portal-release.yml or host-deploy.sh) to pick up changes."
