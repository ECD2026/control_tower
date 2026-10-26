// Title bar at the top of each page: breadcrumb-style title, optional
// description and right-aligned actions. Also hosts the mobile menu button.

import { Menu } from 'lucide-react'

export default function PageHeader({ title, description, actions, onMenu }) {
  return (
    <header
      className="sticky top-0 z-20 border-b backdrop-blur"
      style={{ background: 'color-mix(in srgb, var(--canvas) 85%, transparent)' }}
    >
      <div className="px-4 sm:px-6 min-h-14 py-2 flex items-center gap-3">
        <button className="lg:hidden text-gray-400 hover:text-white" onClick={onMenu}>
          <Menu size={18} />
        </button>
        <div className="min-w-0">
          <h1 className="text-sm font-semibold text-white truncate">{title}</h1>
          {description && <p className="text-xs text-gray-500 truncate">{description}</p>}
        </div>
        <div className="ml-auto flex items-center gap-2">{actions}</div>
      </div>
    </header>
  )
}
