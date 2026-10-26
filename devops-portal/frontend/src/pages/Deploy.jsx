// Deploy: the infrastructure form on the left, live run output on the right.
// The run itself lives in useDeploymentSession (App level), so leaving this
// page does not interrupt the log stream.

import { useEffect, useState } from 'react'
import { Activity, ExternalLink, GitBranch, Terminal } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import InfraForm from '../components/InfraForm'
import LogsPanel from '../components/LogsPanel'
import StatusBadge from '../components/StatusBadge'
import { api } from '../lib/api'

export default function Deploy({ session, navigate, onMenu }) {
  const [credentials, setCredentials] = useState([])
  const { formData, setFormData, status, logs, setLogs, deploymentId, meta, submit, isRunning } = session

  useEffect(() => {
    api('/api/credentials').then(list => {
      setCredentials(list)
      // Pre-select when there is only one choice.
      if (list.length === 1 && !formData.credential_id) {
        setFormData(f => ({ ...f, credential_id: list[0].id, region: list[0].default_region }))
      }
    }).catch(() => {})
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <PageHeader
        title="Deploy"
        description="Provision EC2 with Terraform and configure it with Ansible"
        onMenu={onMenu}
        actions={
          <>
            {deploymentId && (
              <span className="hidden md:flex items-center gap-1.5 text-xs text-gray-500 font-mono">
                <GitBranch size={12} /> {deploymentId.slice(0, 8)}
              </span>
            )}
            {meta.externalUrl && (
              <a href={meta.externalUrl} target="_blank" rel="noreferrer"
                className="btn-ghost py-1 px-2.5 text-xs">
                <ExternalLink size={12} /> GitHub run
              </a>
            )}
            <StatusBadge status={status} />
          </>
        }
      />

      <div className="p-4 sm:p-6 grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
        <div className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-200">
            <Activity size={15} className="text-violet-400" />
            Infrastructure Configuration
          </h2>
          <InfraForm
            formData={formData}
            onChange={setFormData}
            onPlan={() => submit('plan')}
            onDeploy={() => submit('deploy')}
            isRunning={isRunning}
            credentials={credentials}
            onAddCredentials={() => navigate('credentials')}
          />
        </div>

        <div className="flex flex-col gap-3 xl:sticky xl:top-20">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Terminal size={15} className="text-emerald-400" />
              Live Output
              {meta.executionMode && (
                <span className="text-[10px] uppercase tracking-wide text-gray-500 font-normal">
                  via {meta.executionMode.replace('_', ' ')}
                </span>
              )}
            </h2>
            <div className="flex gap-2">
              {status === 'success' && meta.mode === 'deploy' && (
                <button onClick={() => navigate('instances')} className="btn-primary text-xs py-1 px-3">
                  View instances
                </button>
              )}
              {logs.length > 0 && !isRunning && (
                <button onClick={() => setLogs([])} className="btn-ghost text-xs py-1 px-3">Clear</button>
              )}
            </div>
          </div>
          <LogsPanel logs={logs} status={status} />
        </div>
      </div>
    </>
  )
}
