import { useEffect, useRef } from 'react'
import { Terminal, CheckCircle2, XCircle, Clock } from 'lucide-react'

function classifyLine(line) {
  if (line.startsWith('[ERROR]'))    return 'log-error'
  if (line.startsWith('[WARNING]'))  return 'log-warn'
  if (line.includes('✔') || line.includes('Success') || line.includes('successfully'))
                                     return 'log-success'
  if (line.startsWith('[TERRAFORM]'))return 'log-tf'
  if (line.startsWith('[ANSIBLE]'))  return 'log-ansible'
  if (line.startsWith('[INFO]'))     return 'log-info'
  return 'log-default'
}

export default function LogsPanel({ logs = [], status = 'idle' }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const isEmpty = logs.length === 0

  return (
    <div className="card flex flex-col min-h-[520px] max-h-[680px]">
      {/* Terminal header bar */}
      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-gray-800">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500/70" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/70" />
          <div className="w-3 h-3 rounded-full bg-green-500/70" />
        </div>
        <span className="text-xs text-gray-500 font-mono ml-1">
          devops-portal — live output
        </span>
        <span className="ml-auto text-xs text-gray-600 font-mono">
          {logs.length} line{logs.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Log body */}
      <div className="flex-1 overflow-y-auto font-mono text-xs leading-5 space-y-0.5">
        {isEmpty ? (
          <div className="h-full flex flex-col items-center justify-center gap-3 text-gray-700">
            <Terminal size={32} />
            <p className="text-sm">Waiting for logs…</p>
            <p className="text-xs">Fill the form and click <span className="text-gray-500">Generate Plan</span> or <span className="text-gray-500">Deploy</span></p>
          </div>
        ) : (
          <>
            {logs.map((line, i) => (
              <div key={i} className={`px-1 rounded ${classifyLine(line)} whitespace-pre-wrap break-all`}>
                {line}
              </div>
            ))}

            {/* Running cursor */}
            {(status === 'running' || status === 'pending') && (
              <div className="log-success cursor-blink px-1"> </div>
            )}

            {/* Done banner */}
            {status === 'success' && (
              <div className="mt-3 flex items-center gap-2 text-emerald-400 font-semibold">
                <CheckCircle2 size={14} />
                Completed successfully
              </div>
            )}
            {status === 'failed' && (
              <div className="mt-3 flex items-center gap-2 text-red-400 font-semibold">
                <XCircle size={14} />
                Deployment failed — check logs above
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
