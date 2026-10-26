// Instances: every EC2 instance the user deployed through the portal.
//
// Left: the list. Right: the selected instance (#/instances/<id>) with tabs
//   Overview   - details, power actions (pause/resume/restart/terminate) and
//                live CloudWatch numbers read from Prometheus
//   Configure  - day-2 Ansible run (packages + commands) with live logs
//   Monitoring - the Grafana instance dashboard, embedded

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  RefreshCw, Loader2, Server, WifiOff, Rocket, Terminal, CheckCircle2, XCircle,
  Play, Pause, RotateCw, Trash2, Activity, Settings2, Info, ExternalLink, Cpu, ArrowDownUp,
  ShieldCheck, MemoryStick, HardDrive,
} from 'lucide-react'
import PageHeader from '../components/PageHeader'
import LogsPanel from '../components/LogsPanel'
import { PACKAGE_OPTIONS } from '../components/InfraForm'
import { api, openLogStream } from '../lib/api'

const STATE_STYLE = {
  running:    { dot: 'bg-emerald-400', label: 'Running',  text: 'text-emerald-300' },
  pending:    { dot: 'bg-blue-400 animate-pulse',   label: 'Starting', text: 'text-blue-300' },
  stopping:   { dot: 'bg-yellow-400 animate-pulse', label: 'Pausing',  text: 'text-yellow-300' },
  stopped:    { dot: 'bg-yellow-400', label: 'Paused',     text: 'text-yellow-300' },
  terminated: { dot: 'bg-red-500',    label: 'Terminated', text: 'text-red-400' },
  unknown:    { dot: 'bg-gray-500',   label: 'Unknown',    text: 'text-gray-400' },
}
const TRANSITIONAL = new Set(['pending', 'stopping'])

function StateBadge({ state }) {
  const cfg = STATE_STYLE[state] ?? STATE_STYLE.unknown
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${cfg.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  )
}

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function fmtBytes(value) {
  if (value == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = value
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`
}

const fmtPct = (v) => (v == null ? '—' : `${v.toFixed(1)}%`)

// ── Overview tab ───────────────────────────────────────────────────────────

function MetricCard({ icon: Icon, label, value, sub, tone = 'text-violet-300' }) {
  return (
    <div className="card-raised p-3">
      <div className="flex items-center gap-1.5 text-[11px] text-gray-500 uppercase tracking-wide">
        <Icon size={12} className={tone} /> {label}
      </div>
      <div className="text-lg font-semibold text-white mt-1">{value}</div>
      {sub && <div className="text-[10px] text-gray-600">{sub}</div>}
    </div>
  )
}

function OverviewTab({ instance, onAction, action }) {
  const [monitoring, setMonitoring] = useState(null)

  useEffect(() => {
    let cancelled = false
    const load = () => api(`/api/instances/${instance.id}/monitoring`)
      .then(m => { if (!cancelled) setMonitoring(m) })
      .catch(() => {})
    load()
    const timer = setInterval(load, 30000)  // CloudWatch refreshes every ~60s
    return () => { cancelled = true; clearInterval(timer) }
  }, [instance.id])

  const m = monitoring?.metrics ?? {}
  const busy = action.status === 'running'
  const { state } = instance

  const buttons = [
    { id: 'start',  label: 'Resume',  icon: Play,     show: state === 'stopped', cls: 'btn-success' },
    { id: 'stop',   label: 'Pause',   icon: Pause,    show: state === 'running', cls: 'btn-ghost' },
    { id: 'reboot', label: 'Restart', icon: RotateCw, show: state === 'running', cls: 'btn-ghost' },
    { id: 'delete', label: 'Terminate', icon: Trash2, show: state !== 'terminated', cls: 'btn-danger' },
  ]

  return (
    <div className="space-y-5">
      <div>
        <label className="label">Power</label>
        <div className="flex flex-wrap gap-2">
          {buttons.filter(b => b.show).map(({ id, label, icon: Icon, cls }) => (
            <button key={id} onClick={() => onAction(id)} disabled={busy || TRANSITIONAL.has(state)}
              className={`${cls} py-2 px-3.5`}>
              {busy && action.action === id
                ? <Loader2 size={14} className="animate-spin" />
                : <Icon size={14} />}
              {label}
            </button>
          ))}
          {TRANSITIONAL.has(state) && (
            <span className="flex items-center gap-1.5 text-xs text-gray-400">
              <Loader2 size={12} className="animate-spin" /> Waiting for AWS…
            </span>
          )}
        </div>
        {action.message && (
          <p className={`text-xs mt-2 ${action.status === 'failed' ? 'text-red-400' : 'text-emerald-400'}`}>
            {action.message}
          </p>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="label mb-0">Live metrics</label>
          <span className="text-[10px] text-gray-600">CloudWatch via Prometheus · refreshes every 30s</span>
        </div>
        {monitoring?.error ? (
          <p className="text-xs text-yellow-500">{monitoring.error}</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <MetricCard icon={Cpu} label="CPU" value={fmtPct(m.cpu_percent)} />
            <MetricCard icon={ArrowDownUp} label="Network in" value={fmtBytes(m.network_in_bytes)} sub="per period" />
            <MetricCard icon={ArrowDownUp} label="Network out" value={fmtBytes(m.network_out_bytes)} sub="per period" />
            <MetricCard icon={ShieldCheck} label="Status checks" tone="text-emerald-300"
              value={m.status_check_failed == null ? '—' : m.status_check_failed > 0 ? 'Failing' : 'Passing'} />
            <MetricCard icon={MemoryStick} label="Memory" value={fmtPct(m.memory_percent)}
              sub={monitoring?.node_exporter ? 'node_exporter' : 'install Node Exporter'} />
            <MetricCard icon={HardDrive} label="Disk /" value={fmtPct(m.disk_percent)}
              sub={monitoring?.node_exporter ? 'node_exporter' : 'install Node Exporter'} />
          </div>
        )}
        {state === 'running' && m.cpu_percent == null && !monitoring?.error && (
          <p className="hint">New instances show CloudWatch data after 2–5 minutes.</p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
        {[
          ['Instance ID', instance.id],
          ['Region', instance.region],
          ['Type', instance.instance_type],
          ['OS', instance.os_type],
          ['Public IP', instance.public_ip || '—'],
          ['Private IP', instance.private_ip || '—'],
          ['SSH', instance.public_ip ? `${instance.ssh_user}@${instance.public_ip}` : '—'],
          ['Key pair', instance.key_pair_name],
          ['Deployment', instance.deployment_id?.slice(0, 8)],
          ['Last synced', fmtDate(instance.last_seen_at)],
        ].map(([k, v]) => (
          <div key={k} className="min-w-0">
            <div className="text-gray-500">{k}</div>
            <div className="font-mono text-gray-300 truncate" title={v}>{v}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Configure tab ──────────────────────────────────────────────────────────

function ConfigureTab({ instance }) {
  const [packages, setPackages] = useState([])
  const [customCommands, setCustomCommands] = useState('')
  const [status, setStatus] = useState('idle')
  const [logs, setLogs] = useState([])
  const closeStream = useRef(null)

  useEffect(() => () => closeStream.current?.(), [])

  const toggle = (id) =>
    setPackages(prev => (prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]))

  const apply = async () => {
    setLogs([])
    setStatus('pending')
    try {
      const { configuration_id } = await api(`/api/instances/${instance.id}/configure`, {
        method: 'POST',
        body: { packages, custom_commands: customCommands },
      })
      setStatus('running')
      closeStream.current?.()
      closeStream.current = openLogStream(`/api/instances/configurations/${configuration_id}/stream`, {
        onLine: line => setLogs(prev => [...prev, line]),
        onDone: () => api(`/api/instances/configurations/${configuration_id}/status`)
          .then(s => setStatus(s.status)).catch(() => {}),
        onError: () => setStatus(prev => (prev === 'running' ? 'failed' : prev)),
      })
    } catch (err) {
      setStatus('failed')
      setLogs([`[ERROR] ${err.message}`])
    }
  }

  const busy = status === 'pending' || status === 'running'
  const canApply = instance.state === 'running' && (packages.length > 0 || customCommands.trim())

  return (
    <div className="space-y-4">
      <div>
        <label className="label">Packages to install</label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {PACKAGE_OPTIONS.map(pkg => (
            <button key={pkg.id} type="button" onClick={() => toggle(pkg.id)} disabled={busy}
              className={`choice ${packages.includes(pkg.id) ? 'choice-on' : 'choice-off'}`}>
              <span>{pkg.icon}</span> {pkg.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="label">Custom commands</label>
        <textarea className="input resize-none h-20 font-mono text-xs"
          placeholder={"echo 'hello'\nsudo yum install -y htop"}
          value={customCommands} disabled={busy} onChange={e => setCustomCommands(e.target.value)} />
      </div>

      <button type="button" onClick={apply} disabled={busy || !canApply} className="btn-primary">
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Rocket size={14} />}
        {busy ? 'Applying…' : 'Apply with Ansible'}
      </button>
      {instance.state !== 'running' && (
        <p className="text-xs text-yellow-600">Resume the instance to configure it (currently {instance.state}).</p>
      )}

      {(logs.length > 0 || status !== 'idle') && (
        <div className="space-y-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-300">
            <Terminal size={14} className="text-emerald-400" /> Output
            {status === 'success' && <CheckCircle2 size={14} className="text-emerald-400" />}
            {status === 'failed' && <XCircle size={14} className="text-red-400" />}
          </h3>
          <LogsPanel logs={logs} status={status} minHeight="min-h-[320px]" />
        </div>
      )}
    </div>
  )
}

// ── Monitoring tab ─────────────────────────────────────────────────────────

function MonitoringTab({ instance }) {
  const [monitoring, setMonitoring] = useState(null)
  useEffect(() => {
    api(`/api/instances/${instance.id}/monitoring`).then(setMonitoring).catch(() => {})
  }, [instance.id])

  if (!monitoring) {
    return <div className="flex justify-center py-10 text-gray-500"><Loader2 className="animate-spin" size={18} /></div>
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <a href={monitoring.grafana_url} target="_blank" rel="noreferrer" className="btn-ghost text-xs py-1.5 px-3">
          <ExternalLink size={12} /> Open in Grafana
        </a>
        <a href={monitoring.prometheus_url} target="_blank" rel="noreferrer" className="btn-ghost text-xs py-1.5 px-3">
          <ExternalLink size={12} /> Query in Prometheus
        </a>
        {!monitoring.node_exporter && (
          <span className="text-[11px] text-gray-500">
            Install Node Exporter (Configure tab) for memory, disk and load panels.
          </span>
        )}
      </div>
      <iframe
        title={`Grafana – ${instance.id}`}
        src={`${monitoring.grafana_url}&kiosk&theme=dark`}
        className="w-full h-[720px] rounded-lg border"
        style={{ background: 'var(--panel-raised)' }}
      />
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'overview',   label: 'Overview',   icon: Info },
  { id: 'configure',  label: 'Configure',  icon: Settings2 },
  { id: 'monitoring', label: 'Monitoring', icon: Activity },
]

export default function Instances({ params, navigate, onMenu }) {
  const [instances, setInstances] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [tab, setTab] = useState('overview')
  const [showTerminated, setShowTerminated] = useState(false)
  const [action, setAction] = useState({ status: 'idle', action: null, message: '' })

  const selectedId = params[0]
  const selected = instances.find(i => i.id === selectedId)

  const fetchInstances = useCallback(async () => {
    try { setInstances(await api('/api/instances')) }
    catch { /* keep the last list */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchInstances() }, [fetchInstances])

  // Poll quickly while something is starting/stopping, slowly otherwise.
  const anyTransitional = instances.some(i => TRANSITIONAL.has(i.state))
  useEffect(() => {
    const timer = setInterval(fetchInstances, anyTransitional ? 5000 : 30000)
    return () => clearInterval(timer)
  }, [fetchInstances, anyTransitional])

  useEffect(() => {
    setAction({ status: 'idle', action: null, message: '' })
  }, [selectedId])

  const reconcile = async () => {
    setSyncing(true)
    try {
      await api('/api/instances/reconcile', { method: 'POST' })
      await fetchInstances()
    } catch { /* surfaced by the stale list */ }
    finally { setSyncing(false) }
  }

  const runAction = async (id) => {
    if (!selected) return
    if (id === 'delete' && !window.confirm(
      `Terminate ${selected.name || selected.id}? The instance and its data will be destroyed in AWS.`
    )) return

    setAction({ status: 'running', action: id, message: '' })
    try {
      const res = id === 'delete'
        ? await api(`/api/instances/${selected.id}`, { method: 'DELETE' })
        : await api(`/api/instances/${selected.id}/${id}`, { method: 'POST' })
      const verbs = { start: 'resuming', stop: 'pausing', reboot: 'restarting', delete: 'terminated' }
      setAction({ status: 'success', action: id, message: `Instance ${verbs[id]} (${res.state}).` })
      await fetchInstances()
    } catch (err) {
      setAction({ status: 'failed', action: id, message: err.message })
    }
  }

  const visible = instances.filter(i => showTerminated || i.state !== 'terminated')
  const hiddenCount = instances.length - visible.length

  return (
    <>
      <PageHeader
        title={selected ? selected.name || selected.id : 'Instances'}
        description={selected ? `${selected.id} · ${selected.region}` : 'EC2 instances deployed from this portal'}
        onMenu={onMenu}
        actions={
          <>
            <button onClick={reconcile} disabled={syncing} className="btn-ghost text-xs py-1 px-3"
              title="Ask AWS for the current state of every instance">
              <RefreshCw size={13} className={syncing ? 'animate-spin' : ''} /> Sync with AWS
            </button>
          </>
        }
      />

      <div className="p-4 sm:p-6 grid grid-cols-1 xl:grid-cols-5 gap-6">
        {/* List */}
        <div className="xl:col-span-2 flex flex-col gap-2">
          {loading ? (
            <div className="card flex items-center justify-center h-40 text-gray-500">
              <Loader2 size={18} className="animate-spin" />
            </div>
          ) : visible.length === 0 ? (
            <div className="card flex flex-col items-center justify-center h-40 gap-2 text-gray-500">
              <WifiOff size={26} />
              <p className="text-sm">No instances yet</p>
              <button className="btn-primary text-xs py-1 px-3" onClick={() => navigate('deploy')}>
                <Rocket size={12} /> Deploy one
              </button>
            </div>
          ) : (
            <div className="card p-1.5 space-y-1">
              {visible.map(inst => (
                <button
                  key={inst.id}
                  onClick={() => navigate(`instances/${inst.id}`)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg flex items-center gap-3 transition-colors
                    ${inst.id === selectedId ? 'bg-violet-500/10 ring-1 ring-violet-500/40' : 'hover:bg-white/5'}`}
                >
                  <div className="w-8 h-8 rounded-md bg-white/5 flex items-center justify-center shrink-0">
                    <Server size={15} className="text-gray-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-gray-100 truncate">{inst.name || inst.id}</div>
                    <div className="text-[11px] text-gray-500 font-mono truncate">
                      {inst.id} · {inst.instance_type} · {inst.region}
                    </div>
                  </div>
                  <StateBadge state={inst.state} />
                </button>
              ))}
            </div>
          )}
          {hiddenCount > 0 && (
            <button onClick={() => setShowTerminated(v => !v)} className="text-xs text-gray-500 hover:text-gray-300 self-start px-1">
              {showTerminated ? 'Hide' : 'Show'} {hiddenCount} terminated
            </button>
          )}
        </div>

        {/* Detail */}
        <div className="xl:col-span-3">
          {!selected ? (
            <div className="card flex flex-col items-center justify-center h-40 gap-2 text-gray-500">
              <Server size={26} />
              <p className="text-sm">Select an instance to manage or monitor it.</p>
            </div>
          ) : (
            <div className="card p-0">
              <div className="flex items-center gap-1 px-3 border-b">
                {TABS.map(({ id, label, icon: Icon }) => (
                  <button key={id} onClick={() => setTab(id)}
                    className={`tab flex items-center gap-1.5 ${tab === id ? 'tab-active' : ''}`}>
                    <Icon size={13} /> {label}
                  </button>
                ))}
                <div className="ml-auto"><StateBadge state={selected.state} /></div>
              </div>
              <div className="p-5">
                {tab === 'overview' && <OverviewTab instance={selected} onAction={runAction} action={action} />}
                {tab === 'configure' && <ConfigureTab key={selected.id} instance={selected} />}
                {tab === 'monitoring' && <MonitoringTab instance={selected} />}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
