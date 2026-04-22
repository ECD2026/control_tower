import { ExternalLink, ServerCrash, CheckCircle2, Clock, Loader2 } from 'lucide-react'
import StatusBadge from './StatusBadge'

const STATUS_ICON = {
  success: <CheckCircle2 size={14} className="text-emerald-400" />,
  failed:  <ServerCrash  size={14} className="text-red-400" />,
  running: <Loader2      size={14} className="text-blue-400 animate-spin" />,
  pending: <Clock        size={14} className="text-yellow-400" />,
}

function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function DeploymentHistory({ history = [], loading = false, onSelect }) {
  if (loading) {
    return (
      <div className="card flex items-center justify-center h-40 text-gray-600">
        <Loader2 size={20} className="animate-spin mr-2" />
        Loading history…
      </div>
    )
  }

  if (history.length === 0) {
    return (
      <div className="card flex flex-col items-center justify-center h-40 gap-2 text-gray-600">
        <Clock size={28} />
        <p className="text-sm">No deployments yet</p>
      </div>
    )
  }

  return (
    <div className="card p-0 overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
            <th className="text-left px-4 py-3 font-semibold">ID</th>
            <th className="text-left px-4 py-3 font-semibold">Status</th>
            <th className="text-left px-4 py-3 font-semibold hidden md:table-cell">Region</th>
            <th className="text-left px-4 py-3 font-semibold hidden lg:table-cell">Type</th>
            <th className="text-left px-4 py-3 font-semibold hidden sm:table-cell">Created</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60">
          {history.map((row) => (
            <tr
              key={row.id}
              className="hover:bg-gray-800/40 transition-colors group"
            >
              <td className="px-4 py-3 font-mono text-xs text-gray-400">
                {row.id.slice(0, 8)}…
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={row.status} />
              </td>
              <td className="px-4 py-3 text-gray-300 hidden md:table-cell">
                {row.region}
              </td>
              <td className="px-4 py-3 text-gray-400 font-mono text-xs hidden lg:table-cell">
                {row.instance_type} × {row.instances}
              </td>
              <td className="px-4 py-3 text-gray-500 text-xs hidden sm:table-cell">
                {fmtDate(row.created_at)}
              </td>
              <td className="px-4 py-3 text-right">
                <button
                  onClick={() => onSelect?.(row)}
                  className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-blue-400
                             transition-all p-1 rounded"
                  title="View logs"
                >
                  <ExternalLink size={13} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
