// Credentials: the user's AWS access keys + SSH key pair.
//
// Keys are verified with AWS STS on save and stored encrypted by the backend;
// this page never receives the secret key back. A generated private key is
// returned exactly once so the user can download it for their own SSH use.

import { useCallback, useEffect, useState } from 'react'
import {
  KeyRound, Plus, Trash2, Loader2, ShieldCheck, Download, Upload, Sparkles, X,
} from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { api, downloadText } from '../lib/api'
import { REGIONS } from '../components/InfraForm'

const EMPTY = {
  name: '',
  access_key_id: '',
  secret_access_key: '',
  default_region: 'ap-south-1',
  key_pair_name: '',
  key_source: 'generate',  // 'generate' | 'upload'
  ssh_private_key: '',
}

function CredentialForm({ onSaved, onCancel }) {
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const readPem = async (file) => {
    if (!file) return
    set('ssh_private_key', await file.text())
    // Suggest the key pair name from the file name (my-key.pem -> my-key).
    if (!form.key_pair_name) set('key_pair_name', file.name.replace(/\.pem$/i, ''))
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const saved = await api('/api/credentials', {
        method: 'POST',
        body: {
          name: form.name,
          access_key_id: form.access_key_id,
          secret_access_key: form.secret_access_key,
          default_region: form.default_region,
          key_pair_name: form.key_pair_name,
          generate_key_pair: form.key_source === 'generate',
          ssh_private_key: form.key_source === 'upload' ? form.ssh_private_key : null,
        },
      })
      onSaved(saved)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Add AWS credentials</h2>
        <button type="button" onClick={onCancel} className="text-gray-500 hover:text-white">
          <X size={16} />
        </button>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <div className="sm:col-span-2">
          <label className="label">Display name</label>
          <input className="input" required maxLength={64} placeholder="e.g. Sandbox account"
            value={form.name} onChange={e => set('name', e.target.value)} />
        </div>
        <div>
          <label className="label">Access key ID</label>
          <input className="input font-mono text-xs" required placeholder="AKIA…" autoComplete="off"
            value={form.access_key_id} onChange={e => set('access_key_id', e.target.value)} />
        </div>
        <div>
          <label className="label">Secret access key</label>
          <input className="input font-mono text-xs" required type="password" autoComplete="new-password"
            value={form.secret_access_key} onChange={e => set('secret_access_key', e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Default region</label>
          <select className="select" value={form.default_region}
            onChange={e => set('default_region', e.target.value)}>
            {REGIONS.map(r => <option key={r}>{r}</option>)}
          </select>
          <p className="hint">
            Needs EC2 + CloudWatch read/write permissions. Keys are checked with AWS STS before saving.
          </p>
        </div>
      </div>

      <div className="border-t pt-4 space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-200">SSH key pair</h3>
          <p className="hint">
            Used for Ansible configuration. The public key is registered in whichever region you deploy to.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {[
            ['generate', 'Generate new', Sparkles],
            ['upload', 'Upload .pem', Upload],
          ].map(([id, label, Icon]) => (
            <button key={id} type="button" onClick={() => set('key_source', id)}
              className={`choice justify-center ${form.key_source === id ? 'choice-on' : 'choice-off'}`}>
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>

        <div>
          <label className="label">Key pair name</label>
          <input className="input" required pattern="[A-Za-z0-9._\-]{1,64}" placeholder="portal-key"
            value={form.key_pair_name} onChange={e => set('key_pair_name', e.target.value)} />
        </div>

        {form.key_source === 'upload' && (
          <div className="space-y-2">
            <input type="file" accept=".pem,.key,text/plain"
              className="block w-full text-xs text-gray-400 file:mr-3 file:px-3 file:py-1.5 file:rounded-md
                         file:border-0 file:bg-violet-600 file:text-white hover:file:bg-violet-500"
              onChange={e => readPem(e.target.files?.[0])} />
            <textarea className="input font-mono text-[11px] h-28 resize-none" required
              placeholder="-----BEGIN RSA PRIVATE KEY-----"
              value={form.ssh_private_key} onChange={e => set('ssh_private_key', e.target.value)} />
          </div>
        )}
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="btn-ghost">Cancel</button>
        <button type="submit" disabled={busy} className="btn-primary">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
          Verify &amp; save
        </button>
      </div>
    </form>
  )
}

export default function Credentials({ onMenu }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [generated, setGenerated] = useState(null)  // { name, pem } shown once
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try { setItems(await api('/api/credentials')) }
    catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const onSaved = (saved) => {
    setAdding(false)
    if (saved.generated_private_key) {
      setGenerated({ name: saved.key_pair_name, pem: saved.generated_private_key })
    }
    load()
  }

  const remove = async (cred) => {
    if (!window.confirm(`Delete credentials "${cred.name}"? Deployments using them can no longer be managed.`)) return
    setError('')
    try {
      await api(`/api/credentials/${cred.id}`, { method: 'DELETE' })
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <PageHeader
        title="Credentials"
        description="AWS access keys and SSH key pairs used for your deployments"
        onMenu={onMenu}
        actions={!adding && (
          <button className="btn-primary py-1.5 px-3 text-xs" onClick={() => setAdding(true)}>
            <Plus size={13} /> Add credentials
          </button>
        )}
      />

      <div className="p-4 sm:p-6 max-w-4xl w-full space-y-4">
        {generated && (
          <div className="card border-amber-500/40 bg-amber-500/5 flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="flex-1 text-sm">
              <p className="text-amber-200 font-medium">Download your new private key now</p>
              <p className="text-xs text-gray-400 mt-0.5">
                The portal keeps an encrypted copy for automation, but this is the only time it is shown.
              </p>
            </div>
            <div className="flex gap-2">
              <button className="btn-primary py-1.5 px-3 text-xs"
                onClick={() => downloadText(`${generated.name}.pem`, generated.pem)}>
                <Download size={13} /> {generated.name}.pem
              </button>
              <button className="btn-ghost py-1.5 px-3 text-xs" onClick={() => setGenerated(null)}>
                Done
              </button>
            </div>
          </div>
        )}

        {adding && <CredentialForm onSaved={onSaved} onCancel={() => setAdding(false)} />}
        {error && <p className="text-xs text-red-400">{error}</p>}

        {loading ? (
          <div className="card flex items-center justify-center h-32 text-gray-500">
            <Loader2 size={18} className="animate-spin" />
          </div>
        ) : items.length === 0 && !adding ? (
          <div className="card flex flex-col items-center justify-center py-12 gap-3 text-center">
            <KeyRound size={28} className="text-gray-600" />
            <div>
              <p className="text-sm text-gray-300">No credentials yet</p>
              <p className="text-xs text-gray-500 mt-1">
                Add an AWS access key and an SSH key pair to start deploying.
              </p>
            </div>
            <button className="btn-primary py-1.5 px-3 text-xs" onClick={() => setAdding(true)}>
              <Plus size={13} /> Add credentials
            </button>
          </div>
        ) : (
          <div className="grid gap-3">
            {items.map(cred => (
              <div key={cred.id} className="card flex flex-col sm:flex-row sm:items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-orange-500/10 text-orange-300 flex items-center justify-center shrink-0">
                  <KeyRound size={18} />
                </div>
                <div className="flex-1 min-w-0 grid sm:grid-cols-3 gap-x-6 gap-y-1 text-xs">
                  <div className="sm:col-span-3 text-sm font-medium text-white">{cred.name}</div>
                  <div><span className="text-gray-500">Account </span>
                    <span className="font-mono text-gray-300">{cred.account_id}</span></div>
                  <div><span className="text-gray-500">Access key </span>
                    <span className="font-mono text-gray-300">{cred.access_key_id}</span></div>
                  <div><span className="text-gray-500">Region </span>
                    <span className="text-gray-300">{cred.default_region}</span></div>
                  <div className="sm:col-span-3 truncate">
                    <span className="text-gray-500">Key pair </span>
                    <span className="font-mono text-gray-300">{cred.key_pair_name}</span>
                    <span className="text-gray-600"> · {cred.ssh_public_key?.split(' ')[0]}</span>
                  </div>
                </div>
                <button onClick={() => remove(cred)} className="btn-ghost py-1.5 px-3 text-xs hover:text-red-300">
                  <Trash2 size={13} /> Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
