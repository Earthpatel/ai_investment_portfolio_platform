import { useMemo, useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { Plus, Search } from 'lucide-react'
import { useStore, type Holding } from '../lib/store'
import { CHART, inputCls } from './ui'

export function AllocationDonut({ holdings, size = 200 }: { holdings: { ticker: string; weight: number }[]; size?: number }) {
  const data = holdings.filter(h => h.weight > 0).map(h => ({ name: h.ticker, value: +h.weight.toFixed(2) }))
  return (
    <div style={{ height: size }} className="relative">
      <ResponsiveContainer>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="92%" paddingAngle={2} stroke="none" isAnimationActive>
            {data.map((_, i) => <Cell key={i} fill={CHART.series[i % CHART.series.length]} />)}
          </Pie>
          <Tooltip formatter={(v) => `${v}%`} />
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <div className="num text-lg font-semibold">{data.length}</div>
        <div className="text-[11px] text-faint">assets</div>
      </div>
    </div>
  )
}

export function Legend({ holdings }: { holdings: { ticker: string; weight: number }[] }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
      {holdings.map((h, i) => (
        <span key={h.ticker} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: CHART.series[i % CHART.series.length] }} />
          <span className="num">{h.ticker}</span><span className="text-faint">{h.weight.toFixed(1)}%</span>
        </span>
      ))}
    </div>
  )
}

export function TickerSearch({ onPick, exclude = [], sectorFilter }: { onPick: (t: string) => void; exclude?: string[]; sectorFilter?: string | null }) {
  const { universe } = useStore()
  const [q, setQ] = useState('')
  const [focus, setFocus] = useState(false)
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase()
    return universe
      .filter(a => !exclude.includes(a.ticker))
      .filter(a => !sectorFilter || a.sector === sectorFilter || a.industry === sectorFilter)
      .filter(a => !s || a.ticker.toLowerCase().startsWith(s) || a.name.toLowerCase().includes(s))
      .sort((a, b) => (a.ticker.toLowerCase() === s ? -1 : b.ticker.toLowerCase() === s ? 1 : 0))
      .slice(0, 12)
  }, [q, universe, exclude, sectorFilter])
  const pick = (t: string) => { onPick(t); setQ('') }
  return (
    <div className="relative">
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
        <input value={q} onChange={e => setQ(e.target.value)} onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              const t = matches[0]?.ticker ?? q.trim().toUpperCase()
              if (t) pick(t)
            }
          }}
          placeholder="Search ticker or company (e.g. AAPL, Nvidia, SPY)…" className={`${inputCls} pl-9`} aria-label="Search tickers" />
      </div>
      {focus && (matches.length > 0 || q) && (
        <ul className="absolute z-30 mt-1 max-h-80 w-full overflow-auto rounded-xl border border-line bg-panel p-1 shadow-2xl">
          {matches.map(a => (
            <li key={a.ticker}>
              <button type="button" onMouseDown={() => pick(a.ticker)} className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left hover:bg-panel-2">
                <span className="min-w-0">
                  <span className="num font-semibold">{a.ticker}</span>
                  <span className="ml-2 truncate text-[12px] text-muted">{a.name}</span>
                </span>
                <span className="shrink-0 rounded-md bg-panel-2 px-1.5 py-0.5 text-[10px] text-faint">{a.type === 'ETF' ? 'ETF' : a.sector}</span>
              </button>
            </li>
          ))}
          {q && !matches.some(m => m.ticker === q.trim().toUpperCase()) && (
            <li><button type="button" onMouseDown={() => pick(q.trim().toUpperCase())} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[12px] text-muted hover:bg-panel-2">
              <Plus size={14} /> Use “{q.trim().toUpperCase()}” (any ticker yfinance knows)
            </button></li>
          )}
        </ul>
      )}
    </div>
  )
}

export function equalWeights(h: Holding[]): Holding[] {
  if (!h.length) return h
  const base = Math.floor((100 / h.length) * 100) / 100
  const rem = +(100 - base * h.length).toFixed(2)
  return h.map((x, i) => ({ ...x, weight: +(base + (i === 0 ? rem : 0)).toFixed(2) }))
}
