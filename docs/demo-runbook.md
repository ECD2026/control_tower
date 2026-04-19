# Demo Runbook — DevOps Portal

Everything you need to run the full demo from a cold machine.
Run each section in a **separate terminal** — they all stay open during the demo.

---

## Prerequisites (one-time, already done)

- Jenkins running at `http://localhost:8080`
- WSL 2 with Ubuntu installed (`wsl --install -d Ubuntu`)
- Ansible installed inside WSL (`wsl -- bash -lc "ansible --version"`)
- Terraform at `C:\Users\Asus\develop\terraform\terraform.exe`
- Python 3 on Windows (`python --version`)
- Node.js on Windows (`node --version`)
- `agent.jar` downloaded to `C:\Users\Asus\agent.jar`
- `.env` file at `devops-portal/backend/.env` with real AWS keys + Jenkins config

---

## Terminal 1 — Jenkins WSL Agent

This connects your user account (which has WSL access) to Jenkins.
Must be running before you trigger any Jenkins build.

```powershell
cd C:\Users\Asus
java -jar agent.jar `
  -url http://localhost:8080/ `
  -secret 1425c95a3737034285c076bb7ed37790d6135b19840050a7a411da7abb38181c `
  -name "wsl-agent" `
  -webSocket `
  -workDir "C:\ProgramData\Jenkins\agent"
```

**Expected output:**
```
INFO: WebSocket connection open
INFO: Connected
```

Leave this terminal open. If it disconnects, re-run the same command.

> The secret is tied to this Jenkins instance. If Jenkins is reinstalled,
> get the new secret from: Jenkins → Manage Nodes → wsl-agent → Agent command.

---

## Terminal 2 — Backend

```powershell
cd C:\Users\Asus\Documents\GitHub\control_tower\devops-portal\backend
pip install -r requirements.txt   # skip if already done
uvicorn main:app --reload --port 8000
```

**Expected output:**
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Smoke test (in any other terminal):
```powershell
curl.exe http://localhost:8000/health
# → {"status":"healthy","service":"DevOps Automation Portal"}
```

---

## Terminal 3 — Frontend

```powershell
cd C:\Users\Asus\Documents\GitHub\control_tower\devops-portal\frontend
npm install    # skip if node_modules already exists
npm run dev
```

**Expected output:**
```
  VITE ready in ...ms
  ➜  Local:   http://localhost:5173/
```

Open **http://localhost:5173** in your browser.

---

## Demo flow

### 1. Deploy a new instance (Deploy tab)

1. Open `http://localhost:5173` → **Deploy** tab.
2. Fill in the form:
   - Region: `ap-south-1`
   - Instance type: `t2.micro`
   - Key pair name: `automatic`
   - OS: `Amazon Linux`
   - Packages: pick any (e.g. Git, Docker)
3. Click **Deploy**.
4. Watch live logs stream in the right panel — lines prefixed `[JENKINS]` confirm Jenkins is running the build.
5. A Jenkins link appears in the top bar. Click it to open the Jenkins build page.
6. Wait for `[HH:MM:SS] Deployment completed` — status badge turns green.

### 2. Verify the instance exists (Instances tab)

1. Click **Instances** tab.
2. The newly provisioned instance appears with state `running`.
3. Click **Reconcile** to sync state with AWS — confirm `checked: 1`.

### 3. Day-2 configuration (Instances tab)

1. Click the instance row to select it.
2. Tick additional packages (e.g. Nginx).
3. Optionally add custom commands in the text box.
4. Click **Apply configuration**.
5. Live Ansible logs stream in the panel below — watch for `PLAY RECAP` with `failed=0`.

### 4. Deployment history (History tab)

1. Click **History** tab.
2. The deployment row shows execution mode `jenkins` and links to the Jenkins build.
3. Click the row to jump back to the Deploy tab with logs replayed.

---

## Stopping everything

```powershell
# Terminal 3 — frontend
Ctrl+C

# Terminal 2 — backend
Ctrl+C

# Terminal 1 — Jenkins agent
Ctrl+C
```

Jenkins itself keeps running as a Windows service — no action needed.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Backend 500 on `/api/deploy` | `.env` not loaded | Confirm `uvicorn` was started from `devops-portal/backend/` dir |
| Jenkins 404 in portal logs | Wrong job name | Check `JENKINS_JOB_NAME` in `.env` matches Jenkins UI exactly |
| Jenkins build queued but never starts | WSL agent not connected | Re-run Terminal 1 command; check Jenkins → Nodes → wsl-agent is online |
| `terraform: command not found` in Jenkins | Terraform checked inside WSL | Expected — Terraform runs natively on Windows via `runner.py`, not in WSL |
| `ansible: command not found` in Jenkins | Ansible not in WSL | `wsl -- bash -lc "sudo apt install -y ansible"` |
| SSH timeout during Ansible | PEM not in WSL `~/.ssh` | Pipeline copies it automatically; check Jenkins build logs for copy errors |
| `[TIMEOUT] No activity` in portal UI | Old backend still running | Restart `uvicorn` — the keepalive fix requires the new code |
| Instance not in Instances tab | Deploy ran before Phase 2 | Use the backfill SQL in `docs/post-phase-2-configuration.md` §5 |
