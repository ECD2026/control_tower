// Thin fetch wrapper for the portal API.
//
// Auth is an HttpOnly session cookie set by /api/auth/login, so requests only
// need `credentials: 'same-origin'`. A 401 anywhere broadcasts
// `portal:unauthorized`, which App listens for to show the login screen.

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

function detailMessage(data, fallback) {
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  // FastAPI validation errors: [{ loc, msg, ... }]
  if (Array.isArray(detail)) return detail.map(d => d.msg).join('; ')
  return fallback
}

export async function api(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
    signal,
  })

  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }

  if (res.status === 401 && !path.startsWith('/api/auth/')) {
    window.dispatchEvent(new Event('portal:unauthorized'))
  }
  if (!res.ok) {
    throw new ApiError(res.status, detailMessage(data, text || res.statusText))
  }
  return data
}

// Subscribe to one of the backend's SSE log streams. The server sends
// "__DONE__" as the final message. Returns a function that closes the stream.
export function openLogStream(path, { onLine, onDone, onError }) {
  const es = new EventSource(path, { withCredentials: true })
  es.onmessage = (e) => {
    if (e.data === '__DONE__') {
      es.close()
      onDone?.()
      return
    }
    onLine?.(e.data)
  }
  es.onerror = () => {
    es.close()
    onError?.()
  }
  return () => es.close()
}

// Trigger a browser download of text content (used for generated SSH keys).
export function downloadText(filename, content) {
  const url = URL.createObjectURL(new Blob([content], { type: 'application/x-pem-file' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
