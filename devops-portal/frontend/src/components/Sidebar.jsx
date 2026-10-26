// Left-hand navigation in the style of PaaS dashboards (Railway, Render):
// project nav at the top, settings below, the signed-in user pinned at the
// bottom. On small screens it becomes an off-canvas drawer.

import {
  LayoutDashboard, Rocket, Server, Activity, History, KeyRound, LogOut, Boxes, Loader2, X,
} from 'lucide-react'

export const NAV_SECTIONS = [
  {
    title: 'Project',
    items: [
      { id: 'overview',    label: 'Overview',    icon: LayoutDashboard },
      { id: 'deploy',      label: 'Deploy',      icon: Rocket },
      { id: 'instances',   label: 'Instances',   icon: Server },
      { id: 'monitoring',  label: 'Monitoring',  icon: Activity },
      { id: 'deployments', label: 'Deployments', icon: History },
    ],
  },
  {
    title: 'Settings',
    items: [
      { id: 'credentials', label: 'Credentials', icon: KeyRound },
    ],
  },
]

export default function Sidebar({ page, navigate, user, onLogout, deploymentRunning, open, onClose }) {
  return (
    <>
      {/* Backdrop for the mobile drawer */}
      {open && (
        <div className="fixed inset-0 bg-black/60 z-30 lg:hidden" onClick={onClose} />
      )}

      <aside
        className={`fixed lg:sticky top-0 left-0 z-40 h-screen w-60 shrink-0 flex flex-col border-r
          transition-transform lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}
        style={{ background: 'var(--panel)' }}
      >
        {/* Brand */}
        <div className="h-14 px-4 flex items-center gap-2.5 border-b">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-600 flex items-center justify-center">
            <Boxes size={15} className="text-white" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-white">DevOps Portal</div>
            <div className="text-[10px] text-gray-500">AWS · Terraform · Ansible</div>
          </div>
          <button className="ml-auto lg:hidden text-gray-500 hover:text-white" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-5">
          {NAV_SECTIONS.map(section => (
            <div key={section.title}>
              <div className="px-2.5 mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-600">
                {section.title}
              </div>
              <div className="space-y-0.5">
                {section.items.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => { navigate(id); onClose() }}
                    className={`nav-item ${page === id ? 'nav-item-active' : ''}`}
                  >
                    <Icon size={15} className={page === id ? 'text-violet-400' : ''} />
                    {label}
                    {id === 'deploy' && deploymentRunning && (
                      <Loader2 size={12} className="ml-auto animate-spin text-violet-400" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Signed-in user */}
        <div className="border-t p-3 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-violet-500/20 text-violet-300 flex items-center justify-center text-xs font-bold uppercase">
            {user.email.slice(0, 2)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs text-gray-200 truncate" title={user.email}>{user.email}</div>
            <div className="text-[10px] text-gray-600">Signed in</div>
          </div>
          <button
            onClick={onLogout}
            className="p-1.5 rounded-md text-gray-500 hover:text-white hover:bg-white/5"
            title="Sign out"
          >
            <LogOut size={14} />
          </button>
        </div>
      </aside>
    </>
  )
}
