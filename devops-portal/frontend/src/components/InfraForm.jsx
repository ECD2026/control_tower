// The deployment form: which AWS credentials, what to launch, how to
// configure it. The SSH key pair comes from the chosen credential, so the
// form no longer asks for a key pair name.

import { useState } from 'react'
import {
  Cloud, Settings, Box, Zap, Rocket, Plus, X, ToggleLeft, ToggleRight, KeyRound, Activity,
} from 'lucide-react'

export const REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'ap-south-1', 'ap-southeast-1', 'ap-northeast-1',
  'eu-west-1', 'eu-central-1', 'ca-central-1',
]

const INSTANCE_TYPES = [
  't2.micro', 't2.small', 't2.medium', 't2.large',
  't3.micro', 't3.small', 't3.medium', 't3.large',
  'm5.large', 'm5.xlarge', 'c5.large', 'c5.xlarge',
]

export const PACKAGE_OPTIONS = [
  { id: 'docker', label: 'Docker', icon: '🐳' },
  { id: 'nginx', label: 'Nginx', icon: '🌐' },
  { id: 'git', label: 'Git', icon: '📦' },
  { id: 'python3', label: 'Python 3', icon: '🐍' },
  { id: 'nodejs', label: 'Node.js', icon: '⬡' },
  { id: 'node_exporter', label: 'Node Exporter', icon: '📈' },
  { id: 'cadvisor', label: 'cAdvisor', icon: '📊' },
]

function SectionHeader({ icon: Icon, title, color = 'text-violet-400' }) {
  return (
    <div className={`section-title ${color}`}>
      <Icon size={14} />
      <span>{title}</span>
    </div>
  )
}

function Toggle({ on, onClick, title, description }) {
  return (
    <div className="flex items-center justify-between card-raised px-4 py-3">
      <div>
        <p className="text-sm font-medium text-gray-200">{title}</p>
        <p className="text-xs text-gray-500 mt-0.5">{description}</p>
      </div>
      <button type="button" onClick={onClick} className="text-gray-400 hover:text-white transition-colors">
        {on ? <ToggleRight size={28} className="text-emerald-400" /> : <ToggleLeft size={28} />}
      </button>
    </div>
  )
}

export default function InfraForm({
  formData, onChange, onPlan, onDeploy, isRunning, credentials = [], onAddCredentials,
}) {
  const [portInput, setPortInput] = useState('')

  const set = (key, value) => onChange(prev => ({ ...prev, [key]: value }))
  const credential = credentials.find(c => c.id === formData.credential_id)

  const addPort = () => {
    const port = parseInt(portInput)
    if (!isNaN(port) && port > 0 && port <= 65535 &&
      !formData.security_group_ports.includes(port)) {
      set('security_group_ports', [...formData.security_group_ports, port])
    }
    setPortInput('')
  }

  const removePort = (port) =>
    set('security_group_ports', formData.security_group_ports.filter(p => p !== port))

  const togglePackage = (pkg) => {
    const pkgs = formData.packages
    set('packages', pkgs.includes(pkg) ? pkgs.filter(p => p !== pkg) : [...pkgs, pkg])
  }

  return (
    <form onSubmit={e => e.preventDefault()} className="card flex flex-col gap-6">
      {/* ── Account ───────────────────────────────────── */}
      <section>
        <SectionHeader icon={KeyRound} title="AWS account" color="text-orange-300" />
        {credentials.length === 0 ? (
          <div className="card-raised px-4 py-3 flex items-center justify-between gap-3">
            <p className="text-xs text-gray-400">Add AWS credentials and a key pair before deploying.</p>
            <button type="button" onClick={onAddCredentials} className="btn-primary py-1.5 px-3 text-xs">
              <Plus size={13} /> Add
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2 sm:col-span-1">
              <label className="label">Credentials</label>
              <select
                className="select"
                value={formData.credential_id}
                onChange={e => set('credential_id', e.target.value)}
              >
                <option value="">Select…</option>
                {credentials.map(c => (
                  <option key={c.id} value={c.id}>{c.name} ({c.account_id})</option>
                ))}
              </select>
            </div>
            <div className="col-span-2 sm:col-span-1">
              <label className="label">Key pair</label>
              <div className="input opacity-70 font-mono text-xs flex items-center">
                {credential?.key_pair_name ?? '—'}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* ── Infrastructure ────────────────────────────── */}
      <section>
        <SectionHeader icon={Cloud} title="Infrastructure" color="text-blue-400" />

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="label">Name (optional)</label>
            <input
              type="text"
              className="input"
              maxLength={40}
              placeholder="web-tier → instances named web-tier-1, web-tier-2…"
              value={formData.name}
              onChange={e => set('name', e.target.value)}
            />
          </div>

          <div>
            <label className="label">Region</label>
            <select className="select" value={formData.region} onChange={e => set('region', e.target.value)}>
              {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>

          <div>
            <label className="label">Instance Type</label>
            <select
              className="select"
              value={formData.instance_type}
              onChange={e => set('instance_type', e.target.value)}
            >
              {INSTANCE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div>
            <label className="label">Instances</label>
            <input
              type="number"
              className="input"
              min={1} max={10}
              value={formData.instances}
              onChange={e => set('instances', parseInt(e.target.value) || 1)}
            />
          </div>

          <div>
            <label className="label">OS</label>
            <select className="select" value={formData.os_type} onChange={e => set('os_type', e.target.value)}>
              <option value="amazon_linux">Amazon Linux 2</option>
              <option value="ubuntu">Ubuntu 22.04</option>
            </select>
          </div>

          {/* Security Group Ports */}
          <div className="col-span-2">
            <label className="label">Security Group Ports</label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {formData.security_group_ports.map(port => (
                <span key={port} className="tag group">
                  {port}
                  <button
                    type="button"
                    onClick={() => removePort(port)}
                    className="opacity-60 hover:opacity-100 hover:text-red-400 transition-opacity"
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="number"
                className="input w-28"
                placeholder="8080"
                value={portInput}
                onChange={e => setPortInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addPort())}
              />
              <button type="button" onClick={addPort} className="btn-ghost py-2 px-3">
                <Plus size={14} /> Add
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Configuration ─────────────────────────────── */}
      <section>
        <SectionHeader icon={Settings} title="Configuration" color="text-purple-400" />

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="label">Packages to Install</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {PACKAGE_OPTIONS.map(pkg => (
                <button
                  key={pkg.id}
                  type="button"
                  onClick={() => togglePackage(pkg.id)}
                  className={`choice ${formData.packages.includes(pkg.id) ? 'choice-on' : 'choice-off'}`}
                >
                  <span>{pkg.icon}</span>
                  {pkg.label}
                </button>
              ))}
            </div>
            <p className="hint">Node Exporter adds memory/disk metrics on top of CloudWatch.</p>
          </div>

          <div className="col-span-2">
            <label className="label">Custom Commands</label>
            <textarea
              className="input resize-none h-20 font-mono text-xs"
              placeholder={"echo 'Hello World'\napt install -y htop\ncurl https://example.com"}
              value={formData.custom_commands}
              onChange={e => set('custom_commands', e.target.value)}
            />
          </div>
        </div>
      </section>

      {/* ── Deployment ───────────────────────────────── */}
      <section>
        <SectionHeader icon={Box} title="Deployment" color="text-emerald-400" />

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="label">Docker Image</label>
            <input
              type="text"
              className="input font-mono text-xs"
              placeholder="nginx:latest  or  myrepo/myapp:v1.0"
              value={formData.docker_image}
              onChange={e => set('docker_image', e.target.value)}
            />
          </div>
        </div>
      </section>

      {/* ── Monitoring ───────────────────────────────── */}
      <section>
        <SectionHeader icon={Activity} title="Monitoring" color="text-amber-300" />
        <Toggle
          on={formData.detailed_monitoring}
          onClick={() => set('detailed_monitoring', !formData.detailed_monitoring)}
          title="Detailed CloudWatch monitoring"
          description="1-minute metrics in Grafana (about $2/instance/month). Off = free 5-minute metrics."
        />
      </section>

      {/* ── Action Buttons ───────────────────────────── */}
      <div className="flex gap-3 pt-4 border-t">
        <button
          type="button"
          onClick={onPlan}
          disabled={isRunning || !credential}
          className="btn-ghost flex-1 justify-center py-2.5"
        >
          <Zap size={14} />
          {isRunning ? 'Running…' : 'Generate Plan'}
        </button>
        <button
          type="button"
          onClick={onDeploy}
          disabled={isRunning || !credential}
          className="btn-primary flex-1 justify-center"
        >
          <Rocket size={14} />
          {isRunning ? 'Deploying…' : 'Deploy Infrastructure'}
        </button>
      </div>

      {!credential && credentials.length > 0 && (
        <p className="text-xs text-yellow-600 -mt-3 text-center">
          Select the AWS credentials to deploy with
        </p>
      )}
    </form>
  )
}
