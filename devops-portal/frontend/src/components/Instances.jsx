import { useCallback, useEffect, useRef, useState } from 'react'
import {
  RefreshCw, Loader2, ServerCog, Wifi, WifiOff, Rocket, Package, Terminal,
  CheckCircle2, XCircle, Play, Square, Trash2, Activity,
} from 'lucide-react'
import LogsPanel from './LogsPanel'

const API = ''
const EMBED_GRAFANA = false
const DEFAULT_INSTANCE_PACKAGES = ['node_exporter']

const PACKAGE_OPTIONS = [
  { id: 'docker',     label: 'Docker' },
  { id: 'kubernetes', label: 'Kubernetes' },
  { id: 'nginx',      label: 'Nginx' },
  { id: 'git',        label: 'Git' },
  { id: 'python3',    label: 'Python 3' },
  { id: 'nodejs',     label: 'Node.js' },
  { id: 'node_exporter', label: 'Node Exporter' },
  { id: 'cadvisor',      label: 'cAdvisor' },
]

const STATE_STYLE = {
  running:    { dot: 'bg-emerald-400', label: 'Running',    text: 'text-emerald-300' },
  stopped:    { dot: 'bg-yellow-400',  label: 'Stopped',    text: 'text-yellow-300' },
  terminated: { dot: 'bg-red-500',     label: 'Terminated', text: 'text-red-400' },
  unknown:    { dot: 'bg-gray-500',    label: 'Unknown',    text: 'text-gray-400' },
}

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

export default function Instances() {
  const [instances, setInstances] = useState([])
  const [loading, setLoading] = useState(false)
  const [reconciling, setReconciling] = useState(false)
  const [selected, setSelected] = useState(null)  // selected instance object
  const [packages, setPackages] = useState(DEFAULT_INSTANCE_PACKAGES)
  const [customCommands, setCustomCommands] = useState('')
  const [configStatus, setConfigStatus] = useState('idle')
  const [configLogs, setConfigLogs] = useState([])
  const [monitoring, setMonitoring] = useState(null)
  const [reconcileSummary, setReconcileSummary] = useState(null)
  const [instanceAction, setInstanceAction] = useState({
    status: 'idle',
    action: null,
    message: '',
  })
  const esRef = useRef(null)

  const fetchInstances = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/api/instances`)
      if (res.ok) setInstances(await res.json())
    } catch { /* swallow */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchInstances() }, [fetchInstances])
  useEffect(() => () => esRef.current?.close(), [])

  const togglePackage = (pkgId) => {
    setPackages(prev =>
      prev.includes(pkgId) ? prev.filter(p => p !== pkgId) : [...prev, pkgId]
    )
  }

  const selectInstance = (inst) => {
    setSelected(inst)
    setPackages(DEFAULT_INSTANCE_PACKAGES)
    setCustomCommands('')
    setConfigLogs([])
    setConfigStatus('idle')
    setMonitoring(null)
    setInstanceAction({ status: 'idle', action: null, message: '' })
  }

  const openMonitoring = async (inst) => {
    if (!inst) return
    try {
      const res = await fetch(`${API}/api/instances/${inst.id}/monitoring`)
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      if (!data.enabled) {
        setInstanceAction({
          status: 'failed',
          action: 'monitor',
          message: 'Monitoring is not enabled for this instance.',
        })
        return
      }
      if (EMBED_GRAFANA) {
        setMonitoring(data)
      } else {
        window.open(data.grafana_url, '_blank', 'noopener')
      }
    } catch (err) {
      setInstanceAction({
        status: 'failed',
        action: 'monitor',
        message: err.message || 'Unable to open monitoring dashboard.',
      })
    }
  }

  const runInstanceAction = async (action) => {
    if (!selected) return

    if (action === 'delete') {
      const confirmed = window.confirm(
        `Delete instance ${selected.id}? This will terminate it in AWS.`
      )
      if (!confirmed) return
    }

    setInstanceAction({ status: 'running', action, message: '' })

    const endpoint = action === 'delete'
      ? `${API}/api/instances/${selected.id}`
      : `${API}/api/instances/${selected.id}/${action}`
    const method = action === 'delete' ? 'DELETE' : 'POST'

    try {
      const res = await fetch(endpoint, { method })
      if (!res.ok) throw new Error(await res.text())
      const payload = await res.json()

      setSelected(prev => (
        prev && prev.id === selected.id
          ? { ...prev, state: payload.state || prev.state }
          : prev
      ))
      await fetchInstances()

      const verb = action === 'delete' ? 'deleted' : `${action}ed`
      setInstanceAction({
        status: 'success',
        action,
        message: `Instance ${selected.id} ${verb} successfully.`,
      })
    } catch (err) {
      setInstanceAction({
        status: 'failed',
        action,
        message: err.message || `Failed to ${action} instance.`,
      })
    }
  }

  const reconcile = async () => {
    setReconciling(true)
    setReconcileSummary(null)
    try {
      const res = await fetch(`${API}/api/instances/reconcile`, { method: 'POST' })
      if (res.ok) {
        setReconcileSummary(await res.json())
        await fetchInstances()
      } else {
        setReconcileSummary({ error: await res.text() })
      }
    } catch (err) {
      setReconcileSummary({ error: err.message })
    } finally {
      setReconciling(false)
    }
  }

  const applyConfiguration = async () => {
    if (!selected) return
    if (!packages.length && !customCommands.trim()) return

    setConfigLogs([])
    setConfigStatus('pending')

    try {
      const res = await fetch(
        `${API}/api/instances/${selected.id}/configure`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            packages,
            custom_commands: customCommands,
          }),
        }
      )
      if (!res.ok) throw new Error(await res.text())
      const { configuration_id } = await res.json()
      setConfigStatus('running')

      if (esRef.current) esRef.current.close()
      const es = new EventSource(
        `${API}/api/instances/configurations/${configuration_id}/stream`
      )
      esRef.current = es
      es.onmessage = (e) => {
        if (e.data === '__DONE__') {
          es.close()
          fetch(`${API}/api/instances/configurations/${configuration_id}/status`)
            .then(r => r.json())
            .then(({ status }) => setConfigStatus(status))
            .catch(() => {})
          return
        }
        setConfigLogs(prev => [...prev, e.data])
      }
      es.onerror = () => {
        es.close()
        setConfigStatus(prev => prev === 'running' ? 'failed' : prev)
      }
    } catch (err) {
      setConfigStatus('failed')
      setConfigLogs(prev => [...prev, `[ERROR] ${err.message}`])
    }
  }

  const isBusy = configStatus === 'pending' || configStatus === 'running'
  const actionBusy = instanceAction.status === 'running'
  const canStart = selected?.state === 'stopped'
  const canStop = selected?.state === 'running'
  const canDelete = selected?.state !== 'terminated'

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      {/* LEFT: Instance list */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-base font-semibold text-gray-200">
            <ServerCog size={16} className="text-blue-400" />
            Managed Instances
          </h2>
          <div className="flex gap-2">
            <button
              onClick={reconcile}
              disabled={reconciling}
              className="btn-ghost text-xs py-1 px-3"
              title="Ask AWS which of these instances still exist"
            >
              {reconciling
                ? <Loader2 size={13} className="animate-spin" />
                : <Wifi size={13} />}
              Reconcile
            </button>
            <button
              onClick={fetchInstances}
              disabled={loading}
              className="btn-ghost text-xs py-1 px-3"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {reconcileSummary && (
          <div className="card p-3 text-xs text-gray-400">
            {reconcileSummary.error ? (
              <span className="text-red-400">Reconcile failed: {reconcileSummary.error}</span>
            ) : (
              <span>
                Checked <strong className="text-gray-200">{reconcileSummary.checked}</strong>,
                {' '}updated <strong className="text-gray-200">{reconcileSummary.updated}</strong>.
                {reconcileSummary.transitions?.length > 0 && (
                  <span className="block mt-1">
                    {reconcileSummary.transitions.map(t => (
                      <span key={t.instance_id} className="font-mono text-[11px] block text-gray-500">
                        {t.instance_id}: {t.from} → {t.to}
                      </span>
                    ))}
                  </span>
                )}
              </span>
            )}
          </div>
        )}

        {loading ? (
          <div className="card flex items-center justify-center h-40 text-gray-600">
            <Loader2 size={20} className="animate-spin mr-2" />
            Loading instances…
          </div>
        ) : instances.length === 0 ? (
          <div className="card flex flex-col items-center justify-center h-40 gap-2 text-gray-600">
            <WifiOff size={28} />
            <p className="text-sm">No instances tracked yet</p>
            <p className="text-xs">Deploy something from the Deploy tab first</p>
          </div>
        ) : (
          <div className="card p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
                  <th className="text-left px-4 py-3 font-semibold">Instance</th>
                  <th className="text-left px-4 py-3 font-semibold hidden md:table-cell">Region</th>
                  <th className="text-left px-4 py-3 font-semibold">State</th>
                  <th className="text-left px-4 py-3 font-semibold hidden lg:table-cell">IP</th>
                  <th className="text-left px-4 py-3 font-semibold hidden sm:table-cell">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {instances.map(inst => (
                  <tr
                    key={inst.id}
                    onClick={() => selectInstance(inst)}
                    className={`cursor-pointer hover:bg-gray-800/40 transition-colors
                      ${selected?.id === inst.id ? 'bg-blue-500/10' : ''}`}
                  >
                    <td className="px-4 py-3">
                      <div className="font-mono text-xs text-gray-300">{inst.id}</div>
                      <div className="text-[10px] text-gray-600 mt-0.5">
                        {inst.os_type} · {inst.instance_type}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-400 hidden md:table-cell">
                      {inst.region || '—'}
                    </td>
                    <td className="px-4 py-3">
                      <StateBadge state={inst.state} />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-400 hidden lg:table-cell">
                      {inst.public_ip || '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs hidden sm:table-cell">
                      {fmtDate(inst.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* RIGHT: Configure + logs */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-base font-semibold text-gray-200">
            <Package size={16} className="text-emerald-400" />
            {selected ? `Configure ${selected.id}` : 'Select an instance'}
          </h2>
        </div>

        {!selected ? (
          <div className="card flex flex-col items-center justify-center h-40 gap-2 text-gray-600">
            <ServerCog size={28} />
            <p className="text-sm">Click an instance to add packages or run commands.</p>
          </div>
        ) : (
          <div className="card flex flex-col gap-4">
            <div className="text-xs text-gray-500 space-y-1">
              <div><span className="text-gray-600">Deployment: </span>
                <span className="font-mono text-gray-400">{selected.deployment_id}</span></div>
              <div><span className="text-gray-600">Key pair: </span>
                <span className="font-mono text-gray-400">{selected.key_pair_name}</span></div>
              <div><span className="text-gray-600">SSH user: </span>
                <span className="font-mono text-gray-400">{selected.ssh_user}</span></div>
            </div>

            <div>
              <label className="label">Instance actions</label>
              <div className="grid grid-cols-4 gap-2">
                <button
                  type="button"
                  onClick={() => runInstanceAction('start')}
                  disabled={isBusy || actionBusy || !canStart}
                  className="btn-success justify-center py-2"
                >
                  {actionBusy && instanceAction.action === 'start'
                    ? <Loader2 size={14} className="animate-spin" />
                    : <Play size={14} />}
                  Start
                </button>
                <button
                  type="button"
                  onClick={() => runInstanceAction('stop')}
                  disabled={isBusy || actionBusy || !canStop}
                  className="btn-ghost justify-center py-2"
                >
                  {actionBusy && instanceAction.action === 'stop'
                    ? <Loader2 size={14} className="animate-spin" />
                    : <Square size={14} />}
                  Stop
                </button>
                <button
                  type="button"
                  onClick={() => openMonitoring(selected)}
                  disabled={isBusy || actionBusy || selected.state !== 'running'}
                  className="btn-ghost justify-center py-2"
                  title="Open Grafana dashboard for this instance"
                >
                  <Activity size={14} />
                  Monitor
                </button>
                <button
                  type="button"
                  onClick={() => runInstanceAction('delete')}
                  disabled={isBusy || actionBusy || !canDelete}
                  className="flex items-center justify-center gap-2 px-5 py-2 text-white font-semibold text-sm rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed bg-red-600 hover:bg-red-500 active:bg-red-700"
                >
                  {actionBusy && instanceAction.action === 'delete'
                    ? <Loader2 size={14} className="animate-spin" />
                    : <Trash2 size={14} />}
                  Delete
                </button>
              </div>
              {instanceAction.status === 'failed' && (
                <p className="text-xs text-red-400 mt-2">{instanceAction.message}</p>
              )}
              {instanceAction.status === 'success' && (
                <p className="text-xs text-emerald-400 mt-2">{instanceAction.message}</p>
              )}
            </div>

            <div>
              <label className="label">Packages to install</label>
              <div className="grid grid-cols-3 gap-2">
                {PACKAGE_OPTIONS.map(pkg => {
                  const selectedPkg = packages.includes(pkg.id)
                  return (
                    <button
                      key={pkg.id}
                      type="button"
                      onClick={() => togglePackage(pkg.id)}
                      disabled={isBusy}
                      className={`px-3 py-2 rounded-lg border text-xs font-medium transition-colors
                        ${selectedPkg
                          ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300'
                          : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'}`}
                    >
                      {pkg.label}
                    </button>
                  )
                })}
              </div>
            </div>

            <div>
              <label className="label">Custom commands</label>
              <textarea
                className="input resize-none h-20 font-mono text-xs"
                placeholder={"echo 'hello'\napt install -y htop"}
                value={customCommands}
                disabled={isBusy}
                onChange={e => setCustomCommands(e.target.value)}
              />
            </div>

            <button
              type="button"
              onClick={applyConfiguration}
              disabled={
                isBusy ||
                (!packages.length && !customCommands.trim()) ||
                selected.state !== 'running'
              }
              className="btn-success justify-center"
            >
              <Rocket size={14} />
              {isBusy ? 'Applying…' : 'Apply configuration'}
            </button>

            {selected.state !== 'running' && (
              <p className="text-xs text-yellow-600 text-center -mt-2">
                Only running instances can be reconfigured (current state:
                {' '}{selected.state}).
              </p>
            )}
          </div>
        )}

        {(configLogs.length > 0 || configStatus !== 'idle') && (
          <div className="flex flex-col gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-300">
              <Terminal size={14} className="text-emerald-400" />
              Output
              {configStatus === 'success' && (
                <CheckCircle2 size={14} className="text-emerald-400" />
              )}
              {configStatus === 'failed' && (
                <XCircle size={14} className="text-red-400" />
              )}
            </h3>
            <LogsPanel logs={configLogs} status={configStatus} />
          </div>
        )}

        {EMBED_GRAFANA && monitoring?.grafana_url && (
          <div className="card p-0 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
              <h3 className="text-sm font-semibold text-gray-300">Monitoring</h3>
              <button
                type="button"
                onClick={() => setMonitoring(null)}
                className="btn-ghost text-xs py-1 px-3"
              >
                Close
              </button>
            </div>
            <iframe
              title="Grafana Monitoring"
              src={`${monitoring.grafana_url}&kiosk=tv&theme=dark`}
              className="w-full h-[420px]"
            />
          </div>
        )}
      </div>
    </div>
  )
}
