// State for the current Plan/Deploy run, lifted to App level so the live log
// stream keeps running while the user browses other pages (the sidebar shows
// a "deployment running" indicator in the meantime).

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, openLogStream } from './api'

export const DEFAULT_FORM = {
  credential_id: '',
  name: '',
  provider: 'aws',
  region: 'ap-south-1',
  instance_type: 't3.micro',
  instances: 1,
  security_group_ports: [22, 80, 443],
  os_type: 'amazon_linux',
  packages: ['node_exporter'],
  custom_commands: '',
  docker_image: '',
  kubernetes: false,
  replicas: 1,
  detailed_monitoring: true,
}

const EMPTY_META = { executionMode: null, externalRef: null, externalUrl: null, mode: null }

export function useDeploymentSession() {
  const [formData, setFormData] = useState(DEFAULT_FORM)
  const [status, setStatus] = useState('idle')  // idle | pending | running | success | failed
  const [logs, setLogs] = useState([])
  const [deploymentId, setDeploymentId] = useState(null)
  const [meta, setMeta] = useState(EMPTY_META)
  const closeStream = useRef(null)

  useEffect(() => () => closeStream.current?.(), [])

  const refreshStatus = useCallback(async (id) => {
    try {
      const s = await api(`/api/deploy/${id}/status`)
      setStatus(s.status)
      setMeta(m => ({
        ...m,
        executionMode: s.execution_mode,
        externalRef: s.external_ref,
        externalUrl: s.external_url,
      }))
    } catch { /* status is best-effort */ }
  }, [])

  // Attach to a deployment's SSE stream (live, or a replay of stored logs).
  const follow = useCallback((id) => {
    closeStream.current?.()
    setLogs([])
    setDeploymentId(id)
    closeStream.current = openLogStream(`/api/deploy/${id}/stream`, {
      onLine: (line) => {
        setLogs(prev => [...prev, line])
        // The GitHub run URL is recorded a few seconds after dispatch.
        if (line.includes('GitHub run #')) refreshStatus(id)
      },
      onDone: () => refreshStatus(id),
      onError: () => setStatus(prev => (prev === 'running' ? 'failed' : prev)),
    })
  }, [refreshStatus])

  const submit = useCallback(async (mode) => {
    setLogs([])
    setStatus('pending')
    setMeta({ ...EMPTY_META, mode })
    try {
      const res = await api(`/api/${mode}`, { method: 'POST', body: formData })
      setMeta({
        mode,
        executionMode: res.execution_mode,
        externalRef: res.external_ref,
        externalUrl: res.external_url,
      })
      setStatus('running')
      follow(res.deployment_id)
    } catch (err) {
      setStatus('failed')
      setLogs([`[ERROR] ${err.message}`])
    }
  }, [formData, follow])

  return {
    formData, setFormData,
    status, logs, setLogs, deploymentId, meta,
    submit, follow,
    isRunning: status === 'running' || status === 'pending',
  }
}
