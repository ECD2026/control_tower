// Overview: landing page after login - fleet counts, recent deployments and
// a getting-started checklist (credentials → deploy → monitor).

import { useEffect, useState } from 'react'
import {
  Server, Pause, Rocket, KeyRound, CheckCircle2, Circle, Activity, ArrowRight, Loader2,
} from 'lucide-react'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { api } from '../lib/api'

function Stat({ icon: Icon, label, value, tone, onClick }) {
  return (
    <button onClick={onClick} className="card text-left hover:border-violet-500/40 transition-colors">
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <Icon size={14} className={tone} /> {label}
      </div>
      <div className="text-2xl font-semibold text-white mt-2">{value}</div>
    </button>
  )
}

export default function Overview({ user, navigate, onMenu }) {
  const [data, setData] = useState(null)

  useEffect(() => {
    api('/api/overview').then(setData).catch(() => setData(null))
  }, [])

  if (!data) {
    return (
      <>
        <PageHeader title="Overview" onMenu={onMenu} />
        <div className="flex justify-center py-20 text-gray-500"><Loader2 className="animate-spin" /></div>
      </>
    )
  }

  const steps = [
    { done: data.credentials > 0, label: 'Add AWS credentials and an SSH key pair', page: 'credentials' },
    { done: data.deployments.success > 0, label: 'Deploy your first instance', page: 'deploy' },
    { done: data.instances.running > 0, label: 'Watch it in Monitoring', page: 'monitoring' },
  ]

  return (
    <>
      <PageHeader
        title="Overview"
        description={`Signed in as ${user.email} · deployments run on ${data.execution_mode.replace('_', ' ')}`}
        onMenu={onMenu}
        actions={
          <button className="btn-primary text-xs py-1.5 px-3" onClick={() => navigate('deploy')}>
            <Rocket size={13} /> New deployment
          </button>
        }
      />
      <div className="p-4 sm:p-6 space-y-6 max-w-6xl w-full">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Stat icon={Server} label="Running" value={data.instances.running} tone="text-emerald-400"
            onClick={() => navigate('instances')} />
          <Stat icon={Pause} label="Paused" value={data.instances.stopped} tone="text-yellow-400"
            onClick={() => navigate('instances')} />
          <Stat icon={Rocket} label="Deployments" value={data.deployments.total} tone="text-violet-400"
            onClick={() => navigate('deployments')} />
          <Stat icon={KeyRound} label="Credentials" value={data.credentials} tone="text-orange-300"
            onClick={() => navigate('credentials')} />
        </div>

        <div className="grid lg:grid-cols-5 gap-6">
          <div className="card lg:col-span-2 space-y-3">
            <h2 className="text-sm font-semibold text-white">Getting started</h2>
            {steps.map(step => (
              <button key={step.label} onClick={() => navigate(step.page)}
                className="w-full flex items-center gap-3 text-left text-sm group">
                {step.done
                  ? <CheckCircle2 size={16} className="text-emerald-400 shrink-0" />
                  : <Circle size={16} className="text-gray-600 shrink-0" />}
                <span className={step.done ? 'text-gray-500 line-through' : 'text-gray-200'}>{step.label}</span>
                <ArrowRight size={13} className="ml-auto text-gray-600 group-hover:text-gray-300" />
              </button>
            ))}
          </div>

          <div className="card lg:col-span-3 p-0">
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <h2 className="text-sm font-semibold text-white">Recent deployments</h2>
              <button className="text-xs text-gray-500 hover:text-gray-200" onClick={() => navigate('deployments')}>
                View all
              </button>
            </div>
            {data.recent_deployments.length === 0 ? (
              <p className="px-5 py-8 text-sm text-gray-500 text-center">Nothing deployed yet.</p>
            ) : (
              <div className="divide-y divide-[color:var(--line)]">
                {data.recent_deployments.map(d => (
                  <button key={d.id} onClick={() => navigate(`deployments/${d.id}`)}
                    className="w-full px-5 py-3 flex items-center gap-3 text-left hover:bg-white/5">
                    <Activity size={14} className="text-gray-600" />
                    <span className="font-mono text-xs text-gray-400">{d.id.slice(0, 8)}</span>
                    <span className="text-xs text-gray-500 hidden sm:inline">
                      {d.region} · {d.instance_type} × {d.instances}
                    </span>
                    <span className="ml-auto"><StatusBadge status={d.status} /></span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
