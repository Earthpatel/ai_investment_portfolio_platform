import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend as RLegend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Play, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { toRequest, useStore, type Holding, type Settings } from '../lib/store'
import { histogram, pct, usd, usdShort } from '../lib/format'
import { Alert, Button, CHART, Card, PageHeader, Spinner } from '../components/ui'

type Variant = { name: string; holdings: Holding[]; settings: Settings }

export default function Risk() {
  const { holdings, settings, saved, setSaved } = useStore()
  return (
    <div>
      <PageHeader eyebrow="Step 7" title="Risk Analytics">
        Stress-test the portfolio against real historical crises, ask “what if?” one variable at a time, and compare saved scenarios using the same random draws.
      </PageHeader>
      <WhatIf />
      <Compare saved={saved} onClear={(i) => setSaved(saved.filter((_, j) => j !== i))} current={{ name: 'Current', holdings, settings }} />
      <Stress />
    </div>
  )
}

function WhatIf() {
  const { holdings, settings } = useStore()
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const tech: Holding[] = (() => {
    const has = holdings.find(h => h.ticker === 'XLK')
    const scaled = holdings.map(h => ({ ...h, weight: h.weight * 0.8 }))
    return has ? scaled.map(h => h.ticker === 'XLK' ? { ...h, weight: h.weight + 20 } : h) : [...scaled, { ticker: 'XLK', weight: 20 }]
  })()
  const ideas: { label: string; v: Variant }[] = [
    { label: `+$100/month`, v: { name: '+$100/mo', holdings, settings: { ...settings, contribution: (settings.contributionFreq === 'none' ? 0 : settings.contribution) + (settings.contributionFreq === 'monthly' || settings.contributionFreq === 'none' ? 100 : settings.contributionFreq === 'weekly' ? 23 : 1200), contributionFreq: settings.contributionFreq === 'none' ? 'monthly' : settings.contributionFreq } } },
    { label: 'Stop 5 years earlier', v: { name: '−5 years', holdings, settings: { ...settings, years: Math.max(1, settings.years - 5) } } },
    { label: '+20% technology (XLK)', v: { name: '+20% tech', holdings: tech, settings } },
    { label: 'Volatility × 1.5', v: { name: 'Vol ×1.5', holdings, settings: { ...settings, volMult: 1.5 } } },
    { label: 'Inflation 5%', v: { name: 'Inflation 5%', holdings, settings: { ...settings, inflation: 0.05 } } },
    { label: settings.rebalance === 'never' ? 'Rebalance annually' : 'Never rebalance', v: { name: settings.rebalance === 'never' ? 'Annual rebal.' : 'No rebal.', holdings, settings: { ...settings, rebalance: settings.rebalance === 'never' ? 'annual' : 'never' } } },
  ]
  const go = async (i: { label: string; v: Variant }) => {
    setBusy(i.label); setErr(null)
    try {
      const n = Math.min(settings.nSims, 3000)
      const r = await api.compare({ scenarios: [{ ...toRequest(holdings, settings), n_sims: n }, { ...toRequest(i.v.holdings, i.v.settings), n_sims: n }], names: ['Current', i.v.name] })
      setRes({ ...r, label: i.label, years: [settings.years, i.v.settings.years] })
    } catch (e: any) { setErr(e.message) } finally { setBusy(null) }
  }
  const rows: [string, (s: any) => string][] = [
    ['Total contributed', s => usd(s.total_contributed)], ['Median ending value', s => usd(s.median_end)], ['Median in today’s $', s => usd(s.median_end_real)],
    ['10th percentile', s => usd(s.p10_end)], ['90th percentile', s => usd(s.p90_end)], ['P(below contributions)', s => pct(s.prob_below_contributions)],
    ['P(goal)', s => pct(s.prob_goal)], ['Median worst drawdown', s => pct(s.median_max_drawdown)],
  ]
  return (
    <Card title="What-if analysis" subtitle="Change exactly one thing and rerun with the same random seed, so the difference comes from your change and not from luck.">
      <div className="flex flex-wrap gap-2">
        {ideas.map(i => <Button key={i.label} variant="ghost" disabled={!!busy} onClick={() => go(i)}>{busy === i.label ? <Spinner /> : null}{i.label}</Button>)}
      </div>
      {err && <div className="mt-3"><Alert tone="loss">{err}</Alert></div>}
      {res && (
        <div className="mt-4 overflow-x-auto">
          <div className="mb-2 text-[13px] font-medium">{res.label}</div>
          <table className="w-full max-w-2xl text-[13px]">
            <thead className="text-left text-faint"><tr><th className="py-1"></th>{res.scenarios.map((s: any) => <th key={s.name} className="text-right">{s.name}</th>)}<th className="text-right">Change</th></tr></thead>
            <tbody>{rows.map(([l, f]) => {
              const a = res.scenarios[0].summary, b = res.scenarios[1].summary
              const key = { 'Total contributed': 'total_contributed', 'Median ending value': 'median_end', 'Median in today’s $': 'median_end_real', '10th percentile': 'p10_end', '90th percentile': 'p90_end', 'P(below contributions)': 'prob_below_contributions', 'P(goal)': 'prob_goal', 'Median worst drawdown': 'median_max_drawdown' }[l]!
              const d = (b[key] ?? 0) - (a[key] ?? 0)
              const isP = key.startsWith('prob') || key.includes('drawdown')
              return <tr key={l} className="border-t border-line"><td className="py-1.5 text-muted">{l}</td><td className="num text-right">{f(a)}</td><td className="num text-right">{f(b)}</td>
                <td className={`num text-right ${d > 0 ? 'text-gain' : d < 0 ? 'text-loss' : 'text-faint'}`}>{isP ? `${d >= 0 ? '+' : ''}${(d * 100).toFixed(1)} pts` : `${d >= 0 ? '+' : ''}${usd(d)}`}</td></tr>
            })}</tbody>
          </table>
          {res.years[0] !== res.years[1] && <p className="mt-2 text-[12px] text-faint">Note: horizons differ ({res.years[0]} vs {res.years[1]} years), so ending values are at different dates.</p>}
        </div>
      )}
    </Card>
  )
}

function Compare({ saved, current, onClear }: { saved: Variant[]; current: Variant; onClear: (i: number) => void }) {
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const list = [current, ...saved].slice(0, 4)
  const run = async () => {
    setBusy(true); setErr(null)
    try {
      setRes(await api.compare({ scenarios: list.map(v => ({ ...toRequest(v.holdings, v.settings), n_sims: Math.min(v.settings.nSims, 3000) })), names: list.map(v => v.name) }))
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const dists = res ? (() => {
    const all = res.scenarios.flatMap((s: any) => s.terminal).sort((a: number, b: number) => a - b)
    const lo = all[Math.floor(all.length * 0.01)], hi = all[Math.floor(all.length * 0.98)]
    const hs = res.scenarios.map((s: any) => histogram(s.terminal, 30, lo, hi))
    return hs[0].map((b: any, i: number) => ({ x: b.mid, ...Object.fromEntries(res.scenarios.map((s: any, k: number) => [s.name, hs[k][i].count / s.terminal.length])) }))
  })() : []
  return (
    <Card className="mt-5" title="Scenario comparison" subtitle="Save scenarios from the simulator results page (up to 3), then compare them here with common random numbers."
      right={<Button onClick={run} disabled={busy || list.length < 2}>{busy ? <Spinner /> : <Play size={14} />}Compare {list.length}</Button>}>
      <div className="mb-3 flex flex-wrap gap-2">
        {list.map((v, i) => (
          <span key={v.name + i} className="inline-flex items-center gap-2 rounded-lg border border-line bg-panel-2 px-2.5 py-1.5 text-[12px]">
            <i className="h-2.5 w-2.5 rounded-sm" style={{ background: CHART.series[i] }} /><b>{v.name}</b>
            <span className="num text-faint">{v.holdings.map(h => `${h.ticker} ${h.weight.toFixed(0)}%`).join(', ')} · {v.settings.years}y</span>
            {i > 0 && <button onClick={() => onClear(i - 1)} className="text-faint hover:text-loss" aria-label="Remove"><Trash2 size={12} /></button>}
          </span>
        ))}
      </div>
      {list.length < 2 && <p className="text-[13px] text-faint">No saved scenarios yet. Run a simulation and press “Save as scenario”, then change the portfolio and come back.</p>}
      {err && <Alert tone="loss">{err}</Alert>}
      {res && (
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="h-72">
            <ResponsiveContainer>
              <LineChart data={dists}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="x" tickFormatter={usdShort} minTickGap={30} /><YAxis width={40} tickFormatter={v => pct(v, 0)} />
                <Tooltip formatter={(v) => pct(Number(v))} labelFormatter={l => `≈ ${usd(Number(l))}`} /><RLegend />
                {res.scenarios.map((s: any, i: number) => <Line key={s.name} dataKey={s.name} stroke={CHART.series[i]} dot={false} strokeWidth={2} type="monotone" />)}
              </LineChart>
            </ResponsiveContainer>
            <p className="text-center text-[11px] text-faint">Ending-wealth distributions (share of simulations)</p>
          </div>
          <table className="w-full text-[12px]">
            <thead className="text-left text-faint"><tr><th className="py-1">Metric</th>{res.scenarios.map((s: any) => <th key={s.name} className="text-right">{s.name}</th>)}</tr></thead>
            <tbody>{([['Contributed', 'total_contributed', usd], ['Median end', 'median_end', usd], ['10th pct', 'p10_end', usd], ['90th pct', 'p90_end', usd], ['P(< contributions)', 'prob_below_contributions', pct], ['P(goal)', 'prob_goal', pct], ['Median ann. return', 'median_annualized_twr', pct], ['Median max DD', 'median_max_drawdown', pct], ['P(DD > 30%)', 'prob_drawdown_over_30', pct]] as const).map(([l, k, f]) => (
              <tr key={k} className="border-t border-line"><td className="py-1.5 text-muted">{l}</td>{res.scenarios.map((s: any) => <td key={s.name} className="num text-right">{(f as any)(s.summary[k])}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function Stress() {
  const { holdings, settings } = useStore()
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const run = async () => {
    setBusy(true); setErr(null)
    try { setRes(await api.stress({ holdings: toRequest(holdings, settings).holdings, initial: settings.initial || 10000 })) }
    catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const avail = res?.crises.filter((c: any) => c.available) ?? []
  return (
    <Card className="mt-5" title="Historical crisis stress tests" subtitle="Replays what actually happened during past crashes, applied to today’s weights. A stress test, not a prediction that the same event will repeat."
      right={<Button onClick={run} disabled={busy}>{busy ? <Spinner /> : <Play size={14} />}Run stress tests</Button>}>
      {err && <Alert tone="loss">{err}</Alert>}
      {res && (
        <>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={avail.map((c: any) => ({ name: c.label, ret: c.total_return, dd: -c.max_drawdown }))} margin={{ left: 8 }}>
                <CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="name" interval={0} tick={{ fontSize: 10 }} /><YAxis tickFormatter={v => pct(v, 0)} width={44} />
                <Tooltip formatter={(v) => pct(Number(v))} /><RLegend />
                <Bar dataKey="ret" name="Return over the window" fill="var(--loss)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="dd" name="Worst drawdown" fill="var(--warn)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {res.crises.map((c: any) => (
              <div key={c.key} className="rounded-xl border border-line bg-panel-2/50 p-3 text-[12px]">
                <div className="flex justify-between"><b>{c.label}</b><span className="num text-faint">{c.start} → {c.end}</span></div>
                {c.available ? <div className="mt-1 text-muted">{usd(settings.initial || 10000)} would have become <b className="num text-ink">{usd((settings.initial || 10000) * (1 + c.total_return))}</b> ({pct(c.total_return)}), with a worst fall of <b className="num text-loss">{pct(c.max_drawdown)}</b>.
                  {c.proxied.length > 0 && <div className="mt-1 text-warn">Proxied with SPY (no data yet): {c.proxied.join(', ')}</div>}</div>
                  : <div className="mt-1 text-faint">Not enough price history for this window.</div>}
              </div>
            ))}
          </div>
          <p className="mt-3 text-[12px] text-faint">{res.note}</p>
        </>
      )}
    </Card>
  )
}
