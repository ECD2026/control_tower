// Table of past deployments. Rows are clickable; the parent decides what
// selecting one does (the Deployments page shows its log).

import { ExternalLink, Clock, Loader2, Trash2 } from 'lucide-react'
import StatusBadge from './StatusBadge'

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function DeploymentHistory({ history = [], loading = false, onSelect, onDelete, selectedId }) {
  if (loading && history.length === 0) {
    return (
      <div className="card flex items-center justify-center h-40 text-gray-500">
        <Loader2 size={20} className="animate-spin mr-2" />
        Loading history…
      </div>
    )
  }

  if (history.length === 0) {
    return (
      <div className="card flex flex-col items-center justify-center h-40 gap-2 text-gray-500">
        <Clock size={28} />
        <p className="text-sm">No deployments yet</p>
      </div>
    )
  }

  return (
    <div className="card p-0 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-xs text-gray-500 uppercase tracking-wider">
            <th className="text-left px-4 py-3 font-semibold">Deployment</th>
            <th className="text-left px-4 py-3 font-semibold">Status</th>
            <th className="text-left px-4 py-3 font-semibold hidden md:table-cell">Region</th>
            <th className="text-left px-4 py-3 font-semibold hidden lg:table-cell">Type</th>
            <th className="text-left px-4 py-3 font-semibold hidden lg:table-cell">Runner</th>
            <th className="text-left px-4 py-3 font-semibold hidden sm:table-cell">Created</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-[color:var(--line)]">
          {history.map((row) => (
            <tr
              key={row.id}
              onClick={() => onSelect?.(row)}
              className={`cursor-pointer transition-colors ${row.id === selectedId ? 'bg-violet-500/10' : 'hover:bg-white/5'}`}
            >
              <td className="px-4 py-3">
                <div className="text-gray-200">{row.name || <span className="font-mono text-xs">{row.id.slice(0, 8)}</span>}</div>
                <div className="text-[10px] text-gray-600 uppercase tracking-wide">{row.mode}</div>
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={row.status} />
              </td>
              <td className="px-4 py-3 text-gray-300 hidden md:table-cell">{row.region}</td>
              <td className="px-4 py-3 text-gray-400 font-mono text-xs hidden lg:table-cell">
                {row.instance_type} × {row.instances}
              </td>
              <td className="px-4 py-3 text-gray-500 text-xs hidden lg:table-cell">
                {(row.execution_mode || 'local').replace('_', ' ')}
              </td>
              <td className="px-4 py-3 text-gray-500 text-xs hidden sm:table-cell">
                {fmtDate(row.created_at)}
              </td>
              <td className="px-4 py-3 text-right">
                {row.external_url && (
                  <a
                    href={row.external_url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={e => e.stopPropagation()}
                    className="text-gray-500 hover:text-violet-300 inline-flex p-1"
                    title="Open GitHub Actions run"
                  >
                    <ExternalLink size={13} />
                  </a>
                )}
                {onDelete && !['pending', 'running'].includes(row.status) && (
                  <button
                    onClick={e => { e.stopPropagation(); onDelete(row) }}
                    className="text-gray-500 hover:text-red-400 inline-flex p-1"
                    title="Delete from history"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
