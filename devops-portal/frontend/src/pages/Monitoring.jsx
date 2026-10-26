// Monitoring: the Grafana "Fleet Overview" dashboard embedded in the portal.
// Grafana is served on the same origin under /grafana and nginx only lets
// logged-in portal users through, so the iframe needs no separate login.
// The dashboard's hidden `owner` variable scopes it to this user's instances.

import { Activity, ExternalLink } from 'lucide-react'
import PageHeader from '../components/PageHeader'

export default function Monitoring({ user, onMenu }) {
  const owner = encodeURIComponent(user.id)
  const fleetUrl = `/grafana/d/fleet-overview/fleet-overview?orgId=1&var-owner=${owner}&refresh=1m`

  return (
    <>
      <PageHeader
        title="Monitoring"
        description="CloudWatch metrics collected by Prometheus, visualised in Grafana"
        onMenu={onMenu}
        actions={
          <>
            <a href={fleetUrl} target="_blank" rel="noreferrer" className="btn-ghost text-xs py-1 px-3">
              <ExternalLink size={12} /> Grafana
            </a>
            <a href="/prometheus/targets" target="_blank" rel="noreferrer" className="btn-ghost text-xs py-1 px-3">
              <Activity size={12} /> Prometheus targets
            </a>
          </>
        }
      />
      <div className="p-4 sm:p-6 flex-1 flex flex-col gap-3">
        <p className="text-xs text-gray-500">
          Per-instance dashboards are on each instance's <span className="text-gray-300">Monitoring</span> tab.
          New instances appear here 2–5 minutes after launch, once CloudWatch publishes their first datapoints.
        </p>
        <iframe
          title="Fleet overview"
          src={`${fleetUrl}&kiosk&theme=dark`}
          className="w-full flex-1 min-h-[760px] rounded-xl border"
          style={{ background: 'var(--panel)' }}
        />
      </div>
    </>
  )
}
