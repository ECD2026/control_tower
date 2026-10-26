// On-screen replacement for window.confirm / window.alert.
//
//   const [ask, dialog] = useDialog()
//   if (!await ask.confirm({ title, message, confirmLabel, danger })) return
//   await ask.notify({ title, message })
//   ...
//   return <>{dialog} ...</>

import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Info } from 'lucide-react'

function Dialog({ title, message, confirmLabel, cancelLabel, danger, onClose }) {
  const confirmRef = useRef(null)

  useEffect(() => {
    confirmRef.current?.focus()
    const onKey = (e) => { if (e.key === 'Escape') onClose(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const Icon = danger ? AlertTriangle : Info

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(false) }}
    >
      <div role="alertdialog" aria-modal="true" aria-labelledby="dialog-title" aria-describedby="dialog-message"
        className="card-raised w-full max-w-md p-5 shadow-2xl">
        <div className="flex gap-3">
          <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0
            ${danger ? 'bg-red-500/15 text-red-400' : 'bg-violet-500/15 text-violet-300'}`}>
            <Icon size={18} />
          </div>
          <div className="min-w-0">
            <h2 id="dialog-title" className="text-sm font-semibold text-white">{title}</h2>
            <p id="dialog-message" className="text-sm text-gray-400 mt-1 break-words">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          {cancelLabel && (
            <button type="button" className="btn-ghost" onClick={() => onClose(false)}>{cancelLabel}</button>
          )}
          <button ref={confirmRef} type="button" className={danger ? 'btn-danger' : 'btn-primary'}
            onClick={() => onClose(true)}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export function useDialog() {
  const [state, setState] = useState(null)
  const resolver = useRef(null)

  const open = useCallback((opts) => new Promise(resolve => {
    resolver.current?.(false)
    resolver.current = resolve
    setState(opts)
  }), [])

  const close = useCallback((result) => {
    resolver.current?.(result)
    resolver.current = null
    setState(null)
  }, [])

  const ask = useRef({
    confirm: ({ title = 'Are you sure?', message, confirmLabel = 'Confirm', danger = false }) =>
      open({ title, message, confirmLabel, cancelLabel: 'Cancel', danger }),
    notify: ({ title = 'Something went wrong', message, danger = true }) =>
      open({ title, message, confirmLabel: 'OK', danger }),
  }).current

  return [ask, state && <Dialog {...state} onClose={close} />]
}
