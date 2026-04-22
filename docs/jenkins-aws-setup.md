# Jenkins + AWS Configuration Guide

This guide covers the configuration still required on your end before the DevOps
Portal can successfully trigger a Jenkins-backed deployment. It assumes the code
changes described in `docs/devops-portal-jenkins-redesign.md` and
`docs/changes.md` are already merged.

Everything in this document is done in a Jenkins UI or on the Jenkins agent host
— no code changes are required to follow it.

---

## 1. Jenkins agent prerequisites

The pipeline in `jenkins/JenkinsFile` runs every stage on `agent any`. Whichever
agent Jenkins picks must satisfy the following.

### 1.1 Operating system

The pipeline auto-detects the agent OS via `isUnix()` and branches:

- **Linux / macOS agent**: stages run directly with `sh`.
- **Windows agent**: stages run through `wsl -- bash ...`. All Unix tooling
  (Python 3, Terraform, Ansible, SSH, git) must be installed *inside* WSL, not
  natively on Windows. Ansible is Linux-only, so WSL is the only supported
  Windows path.

### 1.2 Installed tools

On a **Linux agent**, install these on the host.  
On a **Windows agent**, install them *inside your WSL distribution* (e.g.
`wsl -d Ubuntu` and then `sudo apt install ...`).

| Tool       | How to verify                  | Notes                                                                                |
| ---------- | ------------------------------ | ------------------------------------------------------------------------------------ |
| Python 3.9+ | `python3 --version`           | Used to build a virtualenv in the workspace.                                         |
| Terraform  | `terraform version`            | Must be on `PATH`. The portal currently targets the `~> 5.0` AWS provider.            |
| Ansible    | `ansible --version`            | Pipeline also `pip install ansible` into the venv, but having the system package avoids slow first-run installs. |
| SSH client | `ssh -V`                       | Required both by Ansible and for the SSH readiness probe in `local_executor.py`.      |
| git        | `git --version`                | Needed for `checkout scm` in the pipeline.                                           |
| pip        | `python3 -m pip --version`     | Must be able to reach PyPI; the pipeline installs Ansible into a local venv.         |

### 1.2.1 Windows + WSL extras

If your Jenkins is on Windows (e.g. `C:\ProgramData\Jenkins\...`):

1. Install WSL 2 and a Linux distro: `wsl --install -d Ubuntu`.
2. Inside WSL: `sudo apt update && sudo apt install -y python3 python3-venv python3-pip git openssh-client ansible unzip curl`.
3. Install Terraform inside WSL (HashiCorp apt repo, or download the linux_amd64 binary).
4. Verify from a Windows cmd prompt:
   ```bat
   wsl -- bash -lc "python3 --version && terraform version && ansible --version && ssh -V"
   ```
5. The pipeline uses `WSLENV` to forward env vars (including path-translated
   `PORTAL_SSH_KEY_FILE` and `SSH_KEY_DIR`) into WSL automatically — no extra
   configuration needed beyond having WSL installed.

If your agent cannot reach PyPI directly, mirror the following wheels on an
internal index and point `pip` at it: `fastapi`, `uvicorn`, `python-dotenv`,
`pydantic`, `aiosqlite`, `boto3`, `ansible`.

### 1.3 Outbound network

- AWS endpoints for the region you plan to deploy into (e.g. `ec2.ap-south-1.amazonaws.com`).
- PyPI (`pypi.org`, `files.pythonhosted.org`) unless you set up a mirror.
- HashiCorp registry (`registry.terraform.io`) for `terraform init`.
- Inbound SSH from the agent to the EC2 instances you provision. The portal
  opens port 22 in the generated security group; make sure the agent's public
  egress IP (or NAT gateway) is not firewalled off from the EC2 public IPs.

---

## 2. Add AWS credentials to Jenkins

The pipeline reads AWS credentials through a single Jenkins credential of kind
**Username with password**, where the username carries the access key ID and
the password carries the secret access key.

### 2.1 Create the credential

1. Go to **Manage Jenkins → Credentials → System → Global credentials (unrestricted)**.
2. Click **Add Credentials**.
3. Fill in:
   - **Kind**: `Username with password`
   - **Scope**: `Global`
   - **Username**: your AWS access key ID (e.g. `AKIAIOSFODNN7EXAMPLE`)
   - **Password**: your AWS secret access key
   - **ID**: `aws-portal-credentials`  *(must match exactly — the pipeline references this ID through `AWS_CREDENTIALS_ID`)*
   - **Description**: `DevOps Portal — AWS access key & secret`
4. Save.

### 2.2 IAM permissions the access key must have

The access key belongs to an IAM user or role. Attach an inline policy with at
least the following EC2 permissions — anything less will cause the Terraform
run inside the Jenkins build to fail with `UnauthorizedOperation`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DevOpsPortalEC2",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:DescribeImages",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeKeyPairs",
        "ec2:CreateSecurityGroup",
        "ec2:DeleteSecurityGroup",
        "ec2:DescribeSecurityGroups",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupEgress",
        "ec2:CreateTags",
        "ec2:DeleteTags"
      ],
      "Resource": "*"
    }
  ]
}
```

### 2.3 Where the pipeline uses the credential

In `jenkins/JenkinsFile` the "Run Portal Deployment" stage wraps the deployment
call in:

```groovy
withCredentials([
  usernamePassword(
    credentialsId: "${env.AWS_CREDENTIALS_ID}",
    usernameVariable: 'AWS_ACCESS_KEY_ID',
    passwordVariable: 'AWS_SECRET_ACCESS_KEY'
  ),
  ...
])
```

That binding exports `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` into the
shell environment. The AWS Terraform provider picks them up automatically, so
no other wiring is needed.

If you prefer to use two **Secret text** credentials instead of one username
credential, change `AWS_CREDENTIALS_ID` in the `environment {}` block of the
pipeline and replace the binding with two `string(credentialsId: ..., variable: ...)`
bindings. The rest of the pipeline stays the same.

---

## 3. Add the SSH key pair to Jenkins

The portal generates Ansible inventory entries that point at
`$SSH_KEY_DIR/<KEY_PAIR_NAME>.pem`. On a Jenkins agent, that directory is
dynamic — the pipeline materialises the key from a Jenkins credential each
build and cleans it up afterwards.

Your local PEM file is at `C:\Users\Asus\Downloads\automatic.pem`. In AWS the
corresponding key pair is named `automatic`.

### 3.1 Create the SSH credential

1. **Manage Jenkins → Credentials → System → Global credentials (unrestricted)
   → Add Credentials**.
2. Fill in:
   - **Kind**: `SSH Username with private key`
   - **Scope**: `Global`
   - **Username**: `ec2-user` (or `ubuntu`; the portal overrides this per
     deployment based on the OS type, so this value is only used if something
     else asks for it).
   - **Private Key**: select **Enter directly** and paste the full contents of
     `C:\Users\Asus\Downloads\automatic.pem`, including the
     `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`
     lines (or OPENSSH equivalents).
   - **Passphrase**: leave empty unless your PEM was created with one.
   - **ID**: `portal-ssh-key`  *(must match exactly — referenced by the pipeline through `SSH_CREDENTIALS_ID`)*
   - **Description**: `DevOps Portal — automatic.pem`
3. Save.

### 3.2 What the pipeline does with the key

At build time the pipeline:

1. Binds the credential through `sshUserPrivateKey`, which writes the key into
   a temporary file referenced by `$PORTAL_SSH_KEY_FILE`.
2. Sets `SSH_KEY_DIR=$WORKSPACE/.ssh-portal`.
3. Copies the key to `$SSH_KEY_DIR/${KEY_PAIR_NAME}.pem` and `chmod 600`s it.
4. Calls `python scripts/run_portal_deployment.py`, which resolves the Ansible
   inventory path using the same `SSH_KEY_DIR` plus the deployment's key pair
   name.
5. Removes `$SSH_KEY_DIR` in the `post → cleanup` block so no key material is
   left in the workspace.

Because the portal form asks for a key pair name, the value you type there
**must match the AWS key pair name** associated with this PEM — `automatic` in
your case. Otherwise Terraform will create instances that do not accept the
key stored in Jenkins.

### 3.3 Using the key from the local executor (optional)

If you run the portal locally (`DEPLOYMENT_RUNNER_MODE=local`) rather than
through Jenkins, the same naming convention applies but against your own
filesystem:

- Put the PEM somewhere stable, e.g. `~/.ssh/automatic.pem` on Linux/WSL.
- Set `SSH_KEY_DIR=~/.ssh` (this is already the default).
- Enter `automatic` as the key pair name in the portal form.

On Windows, the backend routes SSH and Ansible through WSL. The default SSH
key directory is `/home/asus/.ssh` inside WSL (see
`devops-portal/backend/services/local_executor.py`). Either drop a copy of the
PEM in that WSL path, or set `SSH_KEY_DIR` in the backend environment to a
directory you already have populated.

---

## 4. Create the Jenkins pipeline job

1. From the Jenkins dashboard, click **New Item**.
2. **Name**: `devops-portal-deploy` (or whatever you prefer; the name goes into
   `JENKINS_JOB_NAME` below).
3. **Type**: `Pipeline`.
4. Save, then open the job's **Configure** page.
5. Under **Pipeline**:
   - **Definition**: `Pipeline script from SCM`
   - **SCM**: `Git`
   - **Repository URL**: the HTTPS or SSH URL of this repository
   - **Credentials**: a Jenkins credential with read access to the repo
   - **Branches to build**: `*/feature-2` while you validate, then switch to
     `*/main` once the Jenkins path is production-ready
   - **Script Path**: `jenkins/JenkinsFile`
6. Under **Build Triggers**:
   - Leave blank. The portal triggers builds through the Jenkins HTTP API; it
     does not need SCM polling.
7. Under **General → This project is parameterized**:
   - Leave unchecked. The pipeline itself declares `parameters { ... }`, so the
     first run will populate them automatically.
8. Save.

### 4.1 First bootstrap build

The `parameters { ... }` block only becomes active **after the pipeline has
run once**. To populate the parameter list:

1. Click **Build Now**. Jenkins will trigger a parameterless run. It may fail
   validation (`KEY_PAIR_NAME is required`) — that is expected.
2. Re-open the job. You should now see **Build with Parameters** on the left.
3. From this point on, every build (whether triggered by you or by the portal)
   runs through `buildWithParameters`.

---

## 5. Create a Jenkins API token for the portal

The portal backend authenticates to Jenkins using HTTP basic auth with a
username + API token.

1. In Jenkins, click your user menu (top right) → **Configure**.
2. Under **API Token**, click **Add new Token**, give it a name
   (e.g. `devops-portal`), and click **Generate**.
3. Copy the token immediately — Jenkins shows it only once.

If the portal should not act as your user, create a dedicated Jenkins user
(`portal-bot` or similar), grant it:
- **Overall → Read**
- **Job → Read**, **Build**, **Workspace** on the `devops-portal-deploy` job

Then generate an API token for that user instead.

### 5.1 CSRF / crumb

The backend already fetches a crumb through `/crumbIssuer/api/json` and
attaches it to the `buildWithParameters` call (see
`services/jenkins_executor.py`). You do **not** need to disable CSRF
protection.

---

## 6. Point the portal backend at Jenkins

With Jenkins configured, tell the portal backend to use it.

### 6.1 Environment variables

Set these on whatever runs the backend (your machine, a container, a systemd
service). They live in `devops-portal/backend/.env.example` as a template.

| Variable                            | Example                                     | Notes                                                     |
| ----------------------------------- | ------------------------------------------- | --------------------------------------------------------- |
| `DEPLOYMENT_RUNNER_MODE`            | `jenkins`                                   | Switches `get_execution_mode()` to Jenkins.                |
| `JENKINS_BASE_URL`                  | `https://jenkins.internal.example.com`       | No trailing slash.                                         |
| `JENKINS_JOB_NAME`                  | `devops-portal-deploy`                       | Folder paths allowed: `folder/devops-portal-deploy`.       |
| `JENKINS_USER`                      | `portal-bot`                                 | The Jenkins user that owns the API token.                 |
| `JENKINS_API_TOKEN`                 | `11aabb...`                                  | From section 5.                                           |
| `JENKINS_VERIFY_TLS`                | `true`                                       | Set to `false` only against self-signed dev instances.     |
| `JENKINS_POLL_INTERVAL_SECONDS`     | `3`                                          | How often the backend polls Jenkins for progress.          |
| `JENKINS_REQUEST_TIMEOUT_SECONDS`   | `15`                                         | Per-HTTP-call timeout.                                    |

### 6.2 Docker Compose

`devops-portal/docker-compose.yml` already passes every Jenkins-related env
var into the backend container. To use it, put the values into a `.env` file
next to the compose file:

```env
DEPLOYMENT_RUNNER_MODE=jenkins
JENKINS_BASE_URL=https://jenkins.internal.example.com
JENKINS_JOB_NAME=devops-portal-deploy
JENKINS_USER=portal-bot
JENKINS_API_TOKEN=11aabb...
AWS_ACCESS_KEY_ID=  # can stay empty when using jenkins mode
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=ap-south-1
```

### 6.3 Network reachability

The backend must be able to reach `JENKINS_BASE_URL` over HTTPS. If the portal
runs in a container and Jenkins is on the host, use the host's LAN IP (not
`localhost`) or add an `extra_hosts` entry in `docker-compose.yml`.

---

## 7. End-to-end smoke test

1. Start the backend with the Jenkins env vars above.
2. Start the frontend (`npm run dev` from `devops-portal/frontend`).
3. Open the portal, fill in the form:
   - Region: whatever region the `automatic` key pair lives in.
   - Key Pair Name: `automatic` (**must match** the AWS key pair name).
   - Packages: pick something small, e.g. Git only.
4. Click **Generate Plan**.
5. Verify that:
   - The portal shows the **JENKINS** execution badge next to the deployment ID.
   - The deployment ID links out to the Jenkins build UI once Jenkins assigns
     a build number.
   - Log lines prefixed `[JENKINS]` stream into the live output panel.
   - The Jenkins build ends green.
6. If the plan run looks correct, repeat with **Deploy Infrastructure**. Expect
   to see `[TERRAFORM]`, `[SSH]`, and `[ANSIBLE]` lines as the build progresses.

If any of those five checks fail, the following are the usual culprits, in
order:

| Symptom                                                                 | Likely cause                                                                       |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Portal shows `Missing Jenkins configuration: JENKINS_BASE_URL, ...`     | Backend env vars from section 6 were not loaded.                                   |
| Portal hangs at "Triggering Jenkins job" then fails with 401 / 403      | API token is wrong or the `portal-bot` user lacks Build permission.                 |
| Jenkins build stays red with `AWS_ACCESS_KEY_ID ... not set`            | Section 2 credential ID is not `aws-portal-credentials`, or Scope is wrong.        |
| `Terraform: UnauthorizedOperation`                                      | IAM policy in section 2.2 is missing one of the actions.                           |
| Ansible fails with `Identity file ... not accessible` or permission     | Section 3 credential ID is not `portal-ssh-key`, or `chmod 600` did not apply.      |
| SSH probe retries for 300 s then times out                              | The Jenkins agent cannot reach the EC2 public IP. Check security groups / NAT.     |

---

## 8. What changes if you move to production

These are out of scope for this guide but worth knowing before this goes past
dev:

- Move Terraform state to an S3 backend with a DynamoDB lock table; otherwise
  each Jenkins build starts from a fresh local state and cannot `destroy` what
  previous builds created.
- Replace the `Username with password` credential with an AWS OIDC trust so the
  Jenkins controller no longer needs a long-lived access key.
- Scope the `portal-bot` Jenkins user to just the `devops-portal-deploy` job
  through Matrix-based authorization.
- Archive Terraform plans as artifacts before applying (the current pipeline
  archives `main.tf`, `setup.yml`, and `inventory.ini` post-build, but not the
  binary plan file).
