// Sign-in / create-account screen. On success the backend sets the session
// cookie; we only keep the returned user object in memory.

import { useState } from 'react'
import { Boxes, Loader2, LogIn, UserPlus } from 'lucide-react'
import { api } from '../lib/api'

export default function Login({ onAuthenticated }) {
  const [mode, setMode] = useState('login')  // 'login' | 'register'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const user = await api(`/api/auth/${mode}`, {
        method: 'POST',
        body: { email, password },
      })
      onAuthenticated(user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-600 flex items-center justify-center mb-3">
            <Boxes size={22} className="text-white" />
          </div>
          <h1 className="text-lg font-semibold text-white">DevOps Portal</h1>
          <p className="text-sm text-gray-500 mt-1 text-center">
            Provision, configure and monitor EC2 from one place.
          </p>
        </div>

        <form onSubmit={submit} className="card space-y-4">
          <div className="flex rounded-lg border p-0.5 text-sm" style={{ background: 'var(--panel-raised)' }}>
            {[['login', 'Sign in'], ['register', 'Create account']].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => { setMode(id); setError('') }}
                className={`flex-1 py-1.5 rounded-md transition-colors
                  ${mode === id ? 'bg-violet-600 text-white' : 'text-gray-400 hover:text-gray-200'}`}
              >
                {label}
              </button>
            ))}
          </div>

          <div>
            <label className="label" htmlFor="email">Email</label>
            <input
              id="email" type="email" required autoComplete="email" className="input"
              value={email} onChange={e => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="password">Password</label>
            <input
              id="password" type="password" required minLength={8} className="input"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password} onChange={e => setPassword(e.target.value)}
            />
            {mode === 'register' && <p className="hint">At least 8 characters.</p>}
          </div>

          {error && <p className="text-xs text-red-400">{error}</p>}

          <button type="submit" disabled={busy} className="btn-primary w-full justify-center">
            {busy
              ? <Loader2 size={14} className="animate-spin" />
              : mode === 'login' ? <LogIn size={14} /> : <UserPlus size={14} />}
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  )
}
