// Deployments: history of Plan/Deploy runs. Selecting a row replays its
// stored log underneath (or re-attaches to it if it is still running).

import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, RefreshCw, Terminal, Trash2 } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import DeploymentHistory from '../components/DeploymentHistory'
import LogsPanel from '../components/LogsPanel'
import { useDialog } from '../components/ConfirmDialog'
import { api, openLogStream } from '../lib/api'

export default function Deployments({ params, navigate, onMenu }) {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState([])
  const [logStatus, setLogStatus] = useState('idle')
  const [ask, dialog] = useDialog()

  const selectedId = params[0]
  const selected = history.find(h => h.id === selectedId)

  const load = useCallback(async () => {
    setLoading(true)
    try { setHistory(await api('/api/history')) }
    catch { /* keep previous */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const remove = async (row) => {
    if (!await ask.confirm({
      title: 'Delete deployment record?',
      message: `"${row.name || row.id.slice(0, 8)}" will be removed from your deployment history.`,
      confirmLabel: 'Delete',
      danger: true,
    })) return
    try {
      await api(`/api/history/${row.id}`, { method: 'DELETE' })
      if (row.id === selectedId) navigate('deployments')
      load()
    } catch (err) { ask.notify({ title: 'Delete failed', message: err.message }) }
  }

  const clearAll = async () => {
    if (!await ask.confirm({
      title: 'Clear deployment history?',
      message: 'All finished deployments will be removed from your history. Running ones are kept and instances are not affected.',
      confirmLabel: 'Clear history',
      danger: true,
    })) return
    try {
      await api('/api/history', { method: 'DELETE' })
      if (selectedId) navigate('deployments')
      load()
    } catch (err) { ask.notify({ title: 'Clear failed', message: err.message }) }
  }

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
      {dialog}
      <PageHeader
        title="Deployments"
        description="Every plan and deploy run, newest first"
        onMenu={onMenu}
        actions={
          <div className="flex gap-2">
            <button onClick={clearAll} disabled={loading || history.length === 0} className="btn-ghost text-xs py-1 px-3">
              <Trash2 size={13} /> Clear history
            </button>
            <button onClick={load} disabled={loading} className="btn-ghost text-xs py-1 px-3">
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
            </button>
          </div>
        }
      />
      <div className="p-4 sm:p-6 space-y-6">
        <DeploymentHistory
          history={history}
          loading={loading}
          selectedId={selectedId}
          onSelect={row => navigate(`deployments/${row.id}`)}
          onDelete={remove}
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
