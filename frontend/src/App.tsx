import { useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { LayoutDashboard, Briefcase, Activity, Search, BrainCircuit, Target, History, ShieldAlert, GraduationCap, Moon, Sun, Menu, X } from 'lucide-react'
import { useStore } from './lib/store'
import Overview from './pages/Overview'
import Builder from './pages/Builder'
import Simulator from './pages/Simulator'
import Explorer from './pages/Explorer'
import MLPage from './pages/MLPage'
import Optimize from './pages/Optimize'
import Backtest from './pages/Backtest'
import Risk from './pages/Risk'
import Learn from './pages/Learn'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/builder', label: 'Portfolio Builder', icon: Briefcase },
  { to: '/simulate', label: 'Monte Carlo Simulator', icon: Activity },
  { to: '/explorer', label: 'Stock & Sector Explorer', icon: Search },
  { to: '/ml', label: 'AI & Machine Learning', icon: BrainCircuit },
  { to: '/optimize', label: 'Portfolio Optimization', icon: Target },
  { to: '/backtest', label: 'Backtesting', icon: History },
  { to: '/risk', label: 'Risk Analytics', icon: ShieldAlert },
  { to: '/learn', label: 'Learn Monte Carlo', icon: GraduationCap },
]

export default function App() {
  const { theme, setTheme, devMode, apiError, holdings } = useStore()
  const [open, setOpen] = useState(false)
  return (
    <div className="flex min-h-full">
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 shrink-0 border-r border-line bg-panel transition-transform lg:static lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex h-16 items-center gap-2.5 border-b border-line px-5">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <div>
            <div className="font-display text-[15px] font-semibold leading-none">Monte Carlo Lab</div>
            <div className="mt-1 text-[11px] text-faint">Investment scenario research</div>
          </div>
        </div>
        <nav className="space-y-0.5 p-3">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition ${isActive ? 'bg-accent/12 text-accent' : 'text-muted hover:bg-panel-2 hover:text-ink'}`}>
              <Icon size={16} />{label}
            </NavLink>
          ))}
        </nav>
        <div className="absolute inset-x-0 bottom-0 border-t border-line p-4 text-[11px] leading-relaxed text-faint">
          Portfolio: <span className="num text-muted">{holdings.map(h => h.ticker).join(' · ') || 'empty'}</span>
          <p className="mt-2">Educational simulations, not investment advice. Outcomes are not guaranteed.</p>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setOpen(false)} />}

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-line bg-bg/85 px-4 backdrop-blur lg:px-8">
          <button className="lg:hidden" onClick={() => setOpen(o => !o)} aria-label="Menu">{open ? <X /> : <Menu />}</button>
          <div className="hidden text-[13px] text-muted lg:block">If I invest in this, what might it be worth — and what could go wrong?</div>
          <button onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="Toggle theme"
            className="rounded-lg border border-line bg-panel p-2 text-muted hover:text-ink">{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}</button>
        </header>
        {devMode && (
          <div className="border-b border-warn/40 bg-warn/15 px-4 py-2 text-center text-[12px] font-medium text-warn lg:px-8">
            DEVELOPMENT MODE — prices are synthetic test data, not real market data. Unset MC_DEV_SYNTHETIC to use real prices.
          </div>
        )}
        {apiError && <div className="border-b border-loss/40 bg-loss/10 px-4 py-2 text-[12px] text-loss lg:px-8">{apiError}</div>}
        <main className="mx-auto max-w-[1400px] px-4 py-8 lg:px-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/builder" element={<Builder />} />
            <Route path="/simulate" element={<Simulator />} />
            <Route path="/explorer" element={<Explorer />} />
            <Route path="/ml" element={<MLPage />} />
            <Route path="/optimize" element={<Optimize />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/risk" element={<Risk />} />
            <Route path="/learn" element={<Learn />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
