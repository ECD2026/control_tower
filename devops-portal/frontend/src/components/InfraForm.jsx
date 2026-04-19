import { useState } from 'react'
import {
  Cloud, Cpu, Settings, Box, Zap, Rocket, Plus, X, ToggleLeft, ToggleRight
} from 'lucide-react'

const REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'ap-south-1', 'ap-southeast-1', 'ap-northeast-1',
  'eu-west-1', 'eu-central-1', 'ca-central-1',
]

const INSTANCE_TYPES = [
  't2.micro', 't2.small', 't2.medium', 't2.large',
  't3.micro', 't3.small', 't3.medium', 't3.large',
  'm5.large', 'm5.xlarge', 'c5.large', 'c5.xlarge',
]

const PACKAGE_OPTIONS = [
  { id: 'docker', label: 'Docker', icon: '🐳' },
  { id: 'kubernetes', label: 'Kubernetes', icon: '☸️' },
  { id: 'nginx', label: 'Nginx', icon: '🌐' },
  { id: 'git', label: 'Git', icon: '📦' },
  { id: 'python3', label: 'Python 3', icon: '🐍' },
  { id: 'nodejs', label: 'Node.js', icon: '⬡' },
]

function SectionHeader({ icon: Icon, title, color = 'text-blue-400' }) {
  return (
    <div className={`section-title ${color}`}>
      <Icon size={14} />
      <span>{title}</span>
    </div>
  )
}

export default function InfraForm({ formData, onChange, onPlan, onDeploy, isRunning }) {
  const [portInput, setPortInput] = useState('')

  const set = (key, value) => onChange(prev => ({ ...prev, [key]: value }))

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
    <form
      onSubmit={e => e.preventDefault()}
      className="card flex flex-col gap-6"
    >
      {/* ── Infrastructure ────────────────────────────── */}
      <section>
        <SectionHeader icon={Cloud} title="Infrastructure" color="text-blue-400" />

        <div className="grid grid-cols-2 gap-3">
          {/* Provider (locked to AWS) */}
          <div>
            <label className="label">Cloud Provider</label>
            <div className="input flex items-center gap-2 opacity-70 cursor-not-allowed">
              <span className="text-orange-400">⬡</span>
              <span>AWS</span>
            </div>
          </div>

          {/* Region */}
          <div>
            <label className="label">Region</label>
            <select
              className="select"
              value={formData.region}
              onChange={e => set('region', e.target.value)}
            >
              {REGIONS.map(r => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>

          {/* Instance Type */}
          <div>
            <label className="label">Instance Type</label>
            <select
              className="select"
              value={formData.instance_type}
              onChange={e => set('instance_type', e.target.value)}
            >
              {INSTANCE_TYPES.map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          {/* Number of instances */}
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

          {/* Key Pair */}
          <div className="col-span-2">
            <label className="label">Key Pair Name</label>
            <input
              type="text"
              className="input"
              placeholder="my-key-pair"
              value={formData.key_pair_name}
              onChange={e => set('key_pair_name', e.target.value)}
            />
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
              <button
                type="button"
                onClick={addPort}
                className="btn-ghost py-2 px-3"
              >
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
          {/* OS Type */}
          <div className="col-span-2">
            <label className="label">OS Type</label>
            <div className="flex gap-2">
              {[
                { id: 'amazon_linux', label: 'Amazon Linux 2', icon: '🔺' },
                { id: 'ubuntu', label: 'Ubuntu 22.04', icon: '🟠' },
              ].map(os => (
                <button
                  key={os.id}
                  type="button"
                  onClick={() => set('os_type', os.id)}
                  className={`flex-1 flex items-center gap-2 px-3 py-2 rounded-lg border text-sm
                    font-medium transition-colors
                    ${formData.os_type === os.id
                      ? 'border-blue-500 bg-blue-500/10 text-blue-300'
                      : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'}`}
                >
                  <span>{os.icon}</span>
                  {os.label}
                </button>
              ))}
            </div>
          </div>

          {/* Packages */}
          <div className="col-span-2">
            <label className="label">Packages to Install</label>
            <div className="grid grid-cols-3 gap-2">
              {PACKAGE_OPTIONS.map(pkg => {
                const selected = formData.packages.includes(pkg.id)
                return (
                  <button
                    key={pkg.id}
                    type="button"
                    onClick={() => togglePackage(pkg.id)}
                    className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs
                      font-medium transition-colors
                      ${selected
                        ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300'
                        : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'}`}
                  >
                    <span>{pkg.icon}</span>
                    {pkg.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Custom Commands */}
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
          {/* Docker Image */}
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

          {/* Kubernetes toggle */}
          <div className="flex items-center justify-between col-span-2
                          bg-gray-800 rounded-lg px-4 py-3 border border-gray-700">
            <div>
              <p className="text-sm font-medium text-gray-200">Kubernetes Deployment</p>
              <p className="text-xs text-gray-500 mt-0.5">Deploy using k3s lightweight Kubernetes</p>
            </div>
            <button
              type="button"
              onClick={() => set('kubernetes', !formData.kubernetes)}
              className="text-gray-400 hover:text-white transition-colors"
            >
              {formData.kubernetes
                ? <ToggleRight size={28} className="text-emerald-400" />
                : <ToggleLeft size={28} />}
            </button>
          </div>

          {/* Replicas (only if k8s enabled) */}
          {formData.kubernetes && (
            <div>
              <label className="label">Replicas</label>
              <input
                type="number"
                className="input"
                min={1} max={20}
                value={formData.replicas}
                onChange={e => set('replicas', parseInt(e.target.value) || 1)}
              />
            </div>
          )}
        </div>
      </section>

      {/* ── Action Buttons ───────────────────────────── */}
      <div className="flex gap-3 pt-1 border-t border-gray-800">
        <button
          type="button"
          onClick={onPlan}
          disabled={isRunning || !formData.key_pair_name}
          className="btn-primary flex-1 justify-center"
        >
          <Zap size={14} />
          {isRunning ? 'Running…' : 'Generate Plan'}
        </button>
        <button
          type="button"
          onClick={onDeploy}
          disabled={isRunning || !formData.key_pair_name}
          className="btn-success flex-1 justify-center"
        >
          <Rocket size={14} />
          {isRunning ? 'Deploying…' : 'Deploy Infrastructure'}
        </button>
      </div>

      {!formData.key_pair_name && (
        <p className="text-xs text-yellow-600 -mt-3 text-center">
          ⚠ Key Pair Name is required before deploying
        </p>
      )}
    </form>
  )
}
