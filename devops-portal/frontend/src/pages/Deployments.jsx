// Deployments: history of Plan/Deploy runs. Selecting a row replays its
// stored log underneath (or re-attaches to it if it is still running).

import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, RefreshCw, Terminal } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import DeploymentHistory from '../components/DeploymentHistory'
import LogsPanel from '../components/LogsPanel'
import { api, openLogStream } from '../lib/api'

export default function Deployments({ params, navigate, onMenu }) {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState([])
  const [logStatus, setLogStatus] = useState('idle')

  const selectedId = params[0]
  const selected = history.find(h => h.id === selectedId)

  const load = useCallback(async () => {
    setLoading(true)
    try { setHistory(await api('/api/history')) }
    catch { /* keep previous */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  // The stream endpoint replays stored logs for finished runs and follows
  // live ones, so one code path covers both.
  useEffect(() => {
    if (!selectedId) return undefined
    setLogs([])
    setLogStatus('running')
    return openLogStream(`/api/deploy/${selectedId}/stream`, {
      onLine: line => setLogs(prev => [...prev, line]),
      onDone: () => api(`/api/deploy/${selectedId}/status`)
        .then(s => setLogStatus(s.status)).catch(() => setLogStatus('idle')),
      onError: () => setLogStatus('idle'),
    })
  }, [selectedId])

  return (
    <>
      <PageHeader
        title="Deployments"
        description="Every plan and deploy run, newest first"
        onMenu={onMenu}
        actions={
          <button onClick={load} disabled={loading} className="btn-ghost text-xs py-1 px-3">
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        }
      />
      <div className="p-4 sm:p-6 space-y-6">
        <DeploymentHistory
          history={history}
          loading={loading}
          selectedId={selectedId}
          onSelect={row => navigate(`deployments/${row.id}`)}
        />

        {selected && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-200">
                <Terminal size={15} className="text-emerald-400" />
                {selected.name || selected.id.slice(0, 8)} · {selected.mode}
              </h2>
              {selected.external_url && (
                <a href={selected.external_url} target="_blank" rel="noreferrer" className="btn-ghost text-xs py-1 px-3">
                  <ExternalLink size={12} /> GitHub run
                </a>
              )}
            </div>
            <LogsPanel logs={logs} status={logStatus} minHeight="min-h-[360px]" />
          </div>
        )}
      </div>
    </>
  )
}
