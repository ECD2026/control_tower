// Minimal hash router: #/<page>/<param>... e.g. #/instances/i-0abc123.
// Hash routing keeps deep links working behind nginx without server config.

import { useCallback, useEffect, useState } from 'react'

function parse(hash) {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent)
  return { page: parts[0] || 'overview', params: parts.slice(1) }
}

export function useHashRoute() {
  const [route, setRoute] = useState(() => parse(window.location.hash))

  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = useCallback((path) => {
    window.location.hash = path.startsWith('#') ? path : `#/${path.replace(/^\//, '')}`
  }, [])

  return { ...route, navigate }
}
