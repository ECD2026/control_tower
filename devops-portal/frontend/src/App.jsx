import { useState, useEffect, useRef, useCallback } from 'react'
import InfraForm from './components/InfraForm'
import LogsPanel from './components/LogsPanel'
import DeploymentHistory from './components/DeploymentHistory'
import Instances from './components/Instances'
import StatusBadge from './components/StatusBadge'
import {
  Server, Activity, History, Zap, GitBranch, RefreshCw, Terminal, ExternalLink,
  ServerCog,
} from 'lucide-react'

const API = ''  // proxied via Vite → http://localhost:8000

const DEFAULT_FORM = {
  provider: 'aws',
  region: 'us-east-1',
  instance_type: 't2.micro',
  instances: 1,
  key_pair_name: '',
  security_group_ports: [22, 80, 443],
  os_type: 'amazon_linux',
  packages: ['node_exporter'],
  custom_commands: '',
  docker_image: '',
  kubernetes: false,
  replicas: 1,
}

export default function App() {
  const [activeTab, setActiveTab] = useState('deploy')   // 'deploy' | 'history'
  const [formData, setFormData] = useState(DEFAULT_FORM)
  const [status, setStatus] = useState('idle')            // idle | pending | running | success | failed
  const [logs, setLogs] = useState([])
  const [deploymentId, setDeploymentId] = useState(null)
  const [history, setHistory] = useState([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [executionMeta, setExecutionMeta] = useState({
    executionMode: 'local',
    externalRef: null,
    externalUrl: null,
  })
  const esRef = useRef(null)

  const fetchHistory = useCallback(async () => {
    setLoadingHistory(true)
    try {
      const res = await fetch(`${API}/api/history`)
      if (res.ok) setHistory(await res.json())
    } catch { /* swallow */ }
    finally { setLoadingHistory(false) }
  }, [])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  // Clean up EventSource on unmount
  useEffect(() => () => esRef.current?.close(), [])

  const startStream = (id) => {
    if (esRef.current) esRef.current.close()

    const es = new EventSource(`${API}/api/deploy/${id}/stream`)
    esRef.current = es

    es.onmessage = (e) => {
      const data = e.data
      if (data === '__DONE__') {
        es.close()
        // Refresh final status from server
        fetch(`${API}/api/deploy/${id}/status`)
          .then(r => r.json())
          .then(({ status: s, execution_mode, external_ref, external_url }) => {
            setStatus(s)
            setExecutionMeta({
              executionMode: execution_mode || 'local',
              externalRef: external_ref || null,
              externalUrl: external_url || null,
            })
          })
          .catch(() => {})
        fetchHistory()
        return
      }
      setLogs(prev => [...prev, data])
    }

    es.onerror = () => {
      es.close()
      setStatus(prev => prev === 'running' ? 'failed' : prev)
    }
  }

  const submit = async (mode) => {
    setLogs([])
    setStatus('pending')
    setDeploymentId(null)
    setExecutionMeta({
      executionMode: 'local',
      externalRef: null,
      externalUrl: null,
    })

    try {
      const res = await fetch(`${API}/api/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      })

      if (!res.ok) {
        const err = await res.text()
        throw new Error(err)
      }

      const {
        deployment_id,
        execution_mode,
        external_ref,
        external_url,
      } = await res.json()
      setDeploymentId(deployment_id)
      setExecutionMeta({
        executionMode: execution_mode || 'local',
        externalRef: external_ref || null,
        externalUrl: external_url || null,
      })
      setStatus('running')
      startStream(deployment_id)
    } catch (err) {
      setStatus('failed')
      setLogs(prev => [...prev, `[ERROR] ${err.message}`])
    }
  }

  const navItems = [
    { id: 'deploy',    label: 'Deploy',    icon: Zap },
    { id: 'instances', label: 'Instances', icon: ServerCog },
    { id: 'history',   label: 'History',   icon: History },
  ]

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* ── Top Nav ────────────────────────────────────────── */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-screen-xl mx-auto px-6 h-14 flex items-center gap-4">
          {/* Logo */}
          <div className="flex items-center gap-2.5 mr-6">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <Server size={16} className="text-white" />
            </div>
            <span className="font-bold text-base text-white tracking-tight">
              DevOps <span className="text-blue-400">Portal</span>
            </span>
          </div>

          {/* Nav tabs */}
          <nav className="flex gap-1">
            {navItems.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => { setActiveTab(id); if (id === 'history') fetchHistory() }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors
                  ${activeTab === id
                    ? 'bg-gray-800 text-white'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/60'}`}
              >
                <Icon size={14} />
                {label}
              </button>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {/* Active deployment badge */}
            {deploymentId && (
              <>
                <div className="hidden sm:flex items-center gap-2 text-xs text-gray-500 font-mono">
                  <GitBranch size={12} />
                  <span className="truncate max-w-[200px]">{deploymentId}</span>
                </div>
                <div className="hidden md:flex items-center gap-2 text-xs text-gray-500">
                  <span className="uppercase tracking-wide">
                    {executionMeta.executionMode || 'local'}
                  </span>
                  {executionMeta.externalRef && (
                    <span className="font-mono text-gray-600">
                      #{executionMeta.externalRef}
                    </span>
                  )}
                  {executionMeta.externalUrl && (
                    <a
                      href={executionMeta.externalUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300"
                    >
                      <ExternalLink size={12} />
                      Jenkins
                    </a>
                  )}
                </div>
              </>
            )}
            <StatusBadge status={status} />
          </div>
        </div>
      </header>

      {/* ── Main Content ───────────────────────────────────── */}
      <main className="flex-1 max-w-screen-xl mx-auto w-full px-6 py-6">
        {activeTab === 'deploy' && (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            {/* LEFT: Form */}
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-base font-semibold text-gray-200">
                  <Activity size={16} className="text-blue-400" />
                  Infrastructure Configuration
                </h2>
              </div>
              <InfraForm
                formData={formData}
                onChange={setFormData}
                onPlan={() => submit('plan')}
                onDeploy={() => submit('deploy')}
                isRunning={status === 'running' || status === 'pending'}
              />
            </div>

            {/* RIGHT: Logs */}
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-base font-semibold text-gray-200">
                  <Terminal size={16} className="text-emerald-400" />
                  Live Output
                </h2>
                {logs.length > 0 && (
                  <button
                    onClick={() => setLogs([])}
                    className="btn-ghost text-xs py-1 px-3"
                  >
                    Clear
                  </button>
                )}
              </div>
              <LogsPanel logs={logs} status={status} />
            </div>
          </div>
        )}

        {activeTab === 'instances' && (
          <Instances />
        )}

        {activeTab === 'history' && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-base font-semibold text-gray-200">
                <History size={16} className="text-purple-400" />
                Deployment History
              </h2>
              <button
                onClick={fetchHistory}
                disabled={loadingHistory}
                className="btn-ghost text-xs py-1 px-3"
              >
                <RefreshCw size={13} className={loadingHistory ? 'animate-spin' : ''} />
                Refresh
              </button>
            </div>
            <DeploymentHistory
              history={history}
              loading={loadingHistory}
              onSelect={(row) => {
                setDeploymentId(row.id)
                setExecutionMeta({
                  executionMode: row.execution_mode || 'local',
                  externalRef: row.external_ref || null,
                  externalUrl: row.external_url || null,
                })
                setActiveTab('deploy')
              }}
            />
          </div>
        )}
      </main>

      {/* ── Footer ─────────────────────────────────────────── */}
      <footer className="border-t border-gray-800 py-3 text-center text-xs text-gray-600">
        DevOps Automation Portal — Terraform + Ansible + AWS
      </footer>
    </div>
  )
}
