const STATUS_CONFIG = {
  idle:    { label: 'Idle',    dot: 'bg-gray-500',    text: 'text-gray-400',  ring: 'ring-gray-700' },
  pending: { label: 'Pending', dot: 'bg-yellow-400 animate-pulse', text: 'text-yellow-300', ring: 'ring-yellow-700' },
  running: { label: 'Running', dot: 'bg-blue-400 animate-pulse',   text: 'text-blue-300',   ring: 'ring-blue-700'   },
  success: { label: 'Success', dot: 'bg-emerald-400', text: 'text-emerald-300', ring: 'ring-emerald-700' },
  failed:  { label: 'Failed',  dot: 'bg-red-500',     text: 'text-red-400',    ring: 'ring-red-800'    },
}

export default function StatusBadge({ status = 'idle', size = 'sm' }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.idle
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full ring-1 ${cfg.ring}
        bg-gray-900/80 ${cfg.text} text-xs font-semibold uppercase tracking-wide`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  )
}
