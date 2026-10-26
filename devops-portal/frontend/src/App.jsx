// Root component: checks the session, shows Login when signed out, otherwise
// renders the sidebar shell and the page selected by the URL hash.

import { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'

import Sidebar from './components/Sidebar'
import { api } from './lib/api'
import { useHashRoute } from './lib/router'
import { useDeploymentSession } from './lib/useDeploymentSession'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Deploy from './pages/Deploy'
import Instances from './pages/Instances'
import Monitoring from './pages/Monitoring'
import Deployments from './pages/Deployments'
import Credentials from './pages/Credentials'

const PAGES = {
  overview: Overview,
  deploy: Deploy,
  instances: Instances,
  monitoring: Monitoring,
  deployments: Deployments,
  credentials: Credentials,
}

export default function App() {
  const [user, setUser] = useState(undefined)  // undefined = still checking
  const [menuOpen, setMenuOpen] = useState(false)
  const { page, params, navigate } = useHashRoute()
  const session = useDeploymentSession()

  // Restore an existing session cookie on load.
  useEffect(() => {
    api('/api/auth/me').then(setUser).catch(() => setUser(null))
  }, [])

  // Any API call that gets a 401 (expired session) sends us back to login.
  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener('portal:unauthorized', onUnauthorized)
    return () => window.removeEventListener('portal:unauthorized', onUnauthorized)
  }, [])

  const logout = useCallback(async () => {
    try { await api('/api/auth/logout', { method: 'POST' }) } catch { /* ignore */ }
    setUser(null)
    navigate('overview')
  }, [navigate])

  if (user === undefined) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500">
        <Loader2 className="animate-spin" size={20} />
      </div>
    )
  }

  if (!user) {
    return <Login onAuthenticated={(u) => { setUser(u); navigate('overview') }} />
  }

  const Page = PAGES[page] ?? Overview

  return (
    <div className="min-h-screen flex">
      <Sidebar
        page={PAGES[page] ? page : 'overview'}
        navigate={navigate}
        user={user}
        onLogout={logout}
        deploymentRunning={session.isRunning}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />
      <main className="flex-1 min-w-0 flex flex-col">
        <Page
          user={user}
          params={params}
          navigate={navigate}
          session={session}
          onMenu={() => setMenuOpen(true)}
        />
      </main>
    </div>
  )
}
