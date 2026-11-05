/* Shared portfolio + simulation settings.
 * One source of truth for every page, persisted to localStorage and shareable via URL. */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, type Asset, type SimResult } from './api'

export type Holding = { ticker: string; weight: number; customMu?: number; customSigma?: number } // weight in %

export type Settings = {
  initial: number; contribution: number
  contributionFreq: 'none' | 'weekly' | 'monthly' | 'annual'; contributionTiming: 'start' | 'end'
  years: number; nSims: number; method: 'parametric' | 'bootstrap' | 'custom'
  seed: number; rebalance: 'never' | 'monthly' | 'quarterly' | 'semiannual' | 'annual'
  fee: number; inflation: number; drip: boolean; goal: number | null
  window: '1y' | '3y' | '5y' | '10y' | '15y' | '20y' | 'max'; blockMonths: number; volMult: number; useMl: boolean
}

export const DEFAULT_SETTINGS: Settings = {
  initial: 10000, contribution: 500, contributionFreq: 'monthly', contributionTiming: 'start', years: 10,
  nSims: 2000, method: 'parametric', seed: 42, rebalance: 'annual', fee: 0.001, inflation: 0.025,
  drip: true, goal: 100000, window: '10y', blockMonths: 6, volMult: 1, useMl: false,
}

export const PRESETS: { name: string; blurb: string; holdings: Holding[] }[] = [
  { name: 'S&P 500 only', blurb: 'One broad index fund', holdings: [{ ticker: 'SPY', weight: 100 }] },
  { name: 'Three-fund style', blurb: 'US + international stocks + bonds', holdings: [{ ticker: 'VTI', weight: 60 }, { ticker: 'VXUS', weight: 20 }, { ticker: 'BND', weight: 20 }] },
  { name: 'Big Tech tilt', blurb: 'Index core with concentrated tech bets', holdings: [{ ticker: 'SPY', weight: 50 }, { ticker: 'AAPL', weight: 15 }, { ticker: 'MSFT', weight: 15 }, { ticker: 'NVDA', weight: 20 }] },
  { name: 'Sector sampler', blurb: 'Four sectors, equal weight', holdings: [{ ticker: 'XLK', weight: 25 }, { ticker: 'XLV', weight: 25 }, { ticker: 'XLF', weight: 25 }, { ticker: 'XLE', weight: 25 }] },
  { name: 'Dividends + bonds', blurb: 'Lower volatility income mix', holdings: [{ ticker: 'SCHD', weight: 50 }, { ticker: 'BND', weight: 50 }] },
]

export type SavedScenario = { name: string; holdings: Holding[]; settings: Settings }

type Ctx = {
  holdings: Holding[]; setHoldings: (h: Holding[]) => void
  settings: Settings; setSettings: (s: Partial<Settings>) => void
  universe: Asset[]; uniMeta: { sector_etfs: Record<string, string>; etf_holdings: Record<string, string[]> }
  result: SimResult | null; setResult: (r: SimResult | null) => void
  resultKey: string | null; setResultKey: (k: string | null) => void
  saved: SavedScenario[]; setSaved: (s: SavedScenario[]) => void
  devMode: boolean; apiError: string | null
  theme: 'dark' | 'light'; setTheme: (t: 'dark' | 'light') => void
}

const C = createContext<Ctx | null>(null)
const LS = 'mclab.v2'

function loadInitial() {
  try {
    const hash = new URLSearchParams(location.hash.split('?')[1] ?? '').get('cfg')
    if (hash) {
      const j = JSON.parse(atob(decodeURIComponent(hash)))
      return { holdings: j.h as Holding[], settings: { ...DEFAULT_SETTINGS, ...j.s } }
    }
  } catch { /* ignore malformed share links */ }
  try {
    const j = JSON.parse(localStorage.getItem(LS) ?? 'null')
    if (j) return { holdings: j.holdings as Holding[], settings: { ...DEFAULT_SETTINGS, ...j.settings }, saved: j.saved, theme: j.theme }
  } catch { /* storage may be blocked */ }
  return { holdings: PRESETS[2].holdings, settings: DEFAULT_SETTINGS }
}

export function shareUrl(holdings: Holding[], settings: Settings) {
  const cfg = encodeURIComponent(btoa(JSON.stringify({ h: holdings, s: settings })))
  return `${location.origin}${location.pathname}#/builder?cfg=${cfg}`
}

export function toRequest(holdings: Holding[], s: Settings) {
  const total = holdings.reduce((a, h) => a + h.weight, 0) || 1
  return {
    holdings: holdings.map(h => ({
      ticker: h.ticker, weight: h.weight / total,
      custom_mu: s.method === 'custom' ? h.customMu ?? null : null,
      custom_sigma: s.method === 'custom' ? h.customSigma ?? null : null,
    })),
    initial: s.initial, contribution: s.contributionFreq === 'none' ? 0 : s.contribution,
    contribution_freq: s.contributionFreq, contribution_timing: s.contributionTiming, years: s.years,
    n_sims: s.nSims, method: s.method, seed: s.seed, rebalance: s.rebalance, fee_annual: s.fee,
    inflation: s.inflation, drip: s.drip, goal: s.goal, window: s.window, block_months: s.blockMonths,
    stress_vol_mult: s.volMult, use_ml_tilt: s.useMl,
  }
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const init = useMemo(loadInitial, [])
  const [holdings, setHoldings] = useState<Holding[]>(init.holdings)
  const [settings, _set] = useState<Settings>(init.settings)
  const [saved, setSaved] = useState<SavedScenario[]>((init as any).saved ?? [])
  const [theme, setTheme] = useState<'dark' | 'light'>((init as any).theme ?? 'dark')
  const [universe, setUniverse] = useState<Asset[]>([])
  const [uniMeta, setUniMeta] = useState({ sector_etfs: {}, etf_holdings: {} })
  const [result, setResult] = useState<SimResult | null>(null)
  const [resultKey, setResultKey] = useState<string | null>(null)
  const [devMode, setDev] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  useEffect(() => {
    api.universe().then(u => { setUniverse(u.assets); setUniMeta({ sector_etfs: u.sector_etfs, etf_holdings: u.etf_holdings }); setDev(u.dev_synthetic) })
      .catch(e => setApiError(`Cannot reach the Python API (${e.message}). Start it with: cd backend && uvicorn app.main:app --port 8000`))
  }, [])
  useEffect(() => {
    try { localStorage.setItem(LS, JSON.stringify({ holdings, settings, saved, theme })) } catch { /* ignore */ }
  }, [holdings, settings, saved, theme])
  useEffect(() => { document.documentElement.classList.toggle('dark', theme === 'dark') }, [theme])

  const value: Ctx = {
    holdings, setHoldings, settings, setSettings: (s) => _set(prev => ({ ...prev, ...s })),
    universe, uniMeta, result, setResult, resultKey, setResultKey, saved, setSaved, devMode, apiError, theme, setTheme,
  }
  return <C.Provider value={value}>{children}</C.Provider>
}

export const useStore = () => {
  const c = useContext(C)
  if (!c) throw new Error('StoreProvider missing')
  return c
}

/** Key that identifies the inputs a result was computed from — stale results are flagged, never silently reused. */
export const configKey = (h: Holding[], s: Settings) => JSON.stringify(toRequest(h, s))
