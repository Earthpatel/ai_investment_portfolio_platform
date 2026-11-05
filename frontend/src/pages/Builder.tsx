import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, Play, Scale, Share2, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { PRESETS, shareUrl, useStore, type Settings } from '../lib/store'
import { pct, usd } from '../lib/format'
import { AllocationDonut, Legend, TickerSearch, equalWeights } from '../components/shared'
import { Alert, Button, Card, Field, NumberInput, PageHeader, Segmented, SliderNumber, Spinner, inputCls } from '../components/ui'

const SECTORS = ['Information Technology', 'Health Care', 'Financials', 'Energy', 'Consumer Discretionary', 'Consumer Staples', 'Industrials', 'Utilities', 'Real Estate', 'Communication Services', 'Materials']

export default function Builder() {
  const { holdings, setHoldings, settings, setSettings, universe, uniMeta } = useStore()
  const nav = useNavigate()
  const [sector, setSector] = useState<string | null>(null)
  const [adv, setAdv] = useState(false)
  const [copied, setCopied] = useState(false)
  const total = holdings.reduce((a, h) => a + h.weight, 0)
  const s = settings
  const set = (p: Partial<Settings>) => setSettings(p)

  const warnings = useMemo(() => {
    const w: string[] = []
    const stocks = holdings.filter(h => universe.find(u => u.ticker === h.ticker)?.type === 'Stock')
    for (const h of stocks) if (h.weight > 25) w.push(`${h.ticker} is ${h.weight.toFixed(0)}% of the portfolio. A single company this large can dominate outcomes.`)
    const top = Math.max(0, ...holdings.map(h => h.weight))
    if (holdings.length === 1 && stocks.length === 1) w.push('A single-stock portfolio has no diversification.')
    for (const etf of holdings.filter(h => uniMeta.etf_holdings[h.ticker])) {
      const overlap = stocks.filter(st => uniMeta.etf_holdings[etf.ticker].includes(st.ticker)).map(st => st.ticker)
      if (overlap.length) w.push(`${overlap.join(', ')} ${overlap.length > 1 ? 'are' : 'is'} already among the largest holdings of ${etf.ticker} (approximate). You own ${overlap.length > 1 ? 'them' : 'it'} twice.`)
    }
    const bySector: Record<string, number> = {}
    for (const h of holdings) {
      const a = universe.find(u => u.ticker === h.ticker)
      if (a && a.type === 'Stock') bySector[a.sector] = (bySector[a.sector] ?? 0) + h.weight
      else if (a?.industry === 'Sector') bySector[a.sector] = (bySector[a.sector] ?? 0) + h.weight
    }
    for (const [sec, v] of Object.entries(bySector)) if (v > 40) w.push(`${v.toFixed(0)}% sits directly in ${sec}. Sector concentration raises volatility.`)
    if (top === 100 && holdings.length > 1) w.push('One asset holds 100%; the others contribute nothing.')
    return w
  }, [holdings, universe, uniMeta])

  const add = (t: string) => {
    if (holdings.some(h => h.ticker === t) || holdings.length >= 25) return
    setHoldings([...holdings, { ticker: t, weight: holdings.length ? 0 : 100 }])
  }

  return (
    <div>
      <PageHeader eyebrow="Step 1–3" title="Portfolio Builder">
        Choose what to invest in, how much, and for how long. Every other section reads this portfolio, so you only enter it once.
      </PageHeader>

      <div className="mb-5 flex flex-wrap gap-2">
        <span className="self-center text-[12px] text-faint">Educational presets (not recommendations):</span>
        {PRESETS.map(p => (
          <button key={p.name} onClick={() => setHoldings(p.holdings)} title={p.blurb}
            className="rounded-full border border-line bg-panel px-3 py-1.5 text-[12px] hover:border-accent/60">{p.name}</button>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <Card title="1 · What to invest in" subtitle="Search any stock or ETF. Sector labels are GICS classifications from the S&P 500 constituents list."
          right={<div className="flex gap-2">
            <Button variant="ghost" onClick={() => setHoldings(equalWeights(holdings))}><Scale size={14} />Equal weight</Button>
          </div>}>
          <div className="mb-3 flex flex-wrap gap-1.5">
            <button onClick={() => setSector(null)} className={`rounded-full px-2.5 py-1 text-[11px] ${!sector ? 'bg-accent text-white' : 'bg-panel-2 text-muted'}`}>All</button>
            {[...SECTORS, 'Broad Market', 'Bonds', 'International'].map(x => (
              <button key={x} onClick={() => setSector(sector === x ? null : x)} className={`rounded-full px-2.5 py-1 text-[11px] ${sector === x ? 'bg-accent text-white' : 'bg-panel-2 text-muted hover:text-ink'}`}>{x}</button>
            ))}
          </div>
          <TickerSearch onPick={add} exclude={holdings.map(h => h.ticker)} sectorFilter={sector} />

          <div className="mt-4 divide-y divide-line rounded-xl border border-line">
            {holdings.length === 0 && <div className="p-6 text-center text-[13px] text-faint">No assets yet. Search above or pick a preset.</div>}
            {holdings.map((h, i) => {
              const a = universe.find(u => u.ticker === h.ticker)
              return (
                <div key={h.ticker} className="grid grid-cols-[1fr_auto] items-center gap-3 p-3 sm:grid-cols-[180px_1fr_auto]">
                  <div className="min-w-0">
                    <div className="num font-semibold">{h.ticker}</div>
                    <div className="truncate text-[11px] text-faint">{a?.name ?? 'Custom ticker'} · {a?.type === 'ETF' ? a.industry : a?.sector ?? '—'}</div>
                  </div>
                  <div className="col-span-2 flex items-center gap-3 sm:col-span-1">
                    <input type="range" min={0} max={100} step={0.5} value={h.weight} aria-label={`${h.ticker} weight`}
                      onChange={e => setHoldings(holdings.map((x, j) => j === i ? { ...x, weight: +e.target.value } : x))} className="flex-1" />
                    <div className="w-24"><NumberInput value={h.weight} min={0} max={100} step={0.5} suffix="%" onChange={v => setHoldings(holdings.map((x, j) => j === i ? { ...x, weight: v } : x))} /></div>
                  </div>
                  <button aria-label={`Remove ${h.ticker}`} onClick={() => setHoldings(holdings.filter((_, j) => j !== i))} className="row-start-1 justify-self-end text-faint hover:text-loss sm:row-start-auto"><Trash2 size={16} /></button>
                </div>
              )
            })}
          </div>
          <div className={`mt-3 flex items-center justify-between rounded-lg px-3 py-2 text-[13px] ${Math.abs(total - 100) < 0.01 ? 'bg-gain/10 text-gain' : 'bg-loss/10 text-loss'}`}>
            <span>Total allocation</span>
            <span className="num font-semibold">{total.toFixed(2)}% {Math.abs(total - 100) >= 0.01 && '(must equal 100%)'}</span>
          </div>
          {Math.abs(total - 100) >= 0.01 && total > 0 && (
            <button onClick={() => setHoldings(holdings.map(h => ({ ...h, weight: +(h.weight / total * 100).toFixed(2) })))} className="mt-2 text-[12px] text-accent hover:underline">Scale weights to 100%</button>
          )}
          {warnings.length > 0 && <div className="mt-4 space-y-2">{warnings.map((w, i) => <Alert key={i}>{w}</Alert>)}</div>}
        </Card>

        <Card title="Allocation">
          <AllocationDonut holdings={holdings} size={230} />
          <div className="mt-3"><Legend holdings={holdings} /></div>
        </Card>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Card title="2 · Money & time">
          <div className="space-y-5">
            <Field label="Initial investment" tip="Money invested on day one.">
              <div className="flex flex-wrap items-center gap-2">
                <div className="w-40"><NumberInput value={s.initial} min={0} max={1e9} step={500} prefix="$" onChange={v => set({ initial: v })} /></div>
                {[1000, 5000, 10000, 50000].map(v => (
                  <button key={v} onClick={() => set({ initial: v })} className={`rounded-md px-2.5 py-1.5 text-[12px] ${s.initial === v ? 'bg-accent text-white' : 'bg-panel-2 text-muted'}`}>{usd(v)}</button>
                ))}
              </div>
            </Field>
            <Field label="Recurring contributions" tip="Weekly contributions are modelled as 52/12 deposits per month (the simulator steps monthly).">
              <div className="flex flex-wrap items-center gap-3">
                <Segmented value={s.contributionFreq} onChange={v => set({ contributionFreq: v })}
                  options={[{ value: 'none', label: 'None' }, { value: 'weekly', label: 'Weekly' }, { value: 'monthly', label: 'Monthly' }, { value: 'annual', label: 'Annual' }]} />
                {s.contributionFreq !== 'none' && <div className="w-36"><NumberInput value={s.contribution} min={0} step={50} prefix="$" onChange={v => set({ contribution: v })} /></div>}
              </div>
            </Field>
            <Field label="Investment horizon">
              <SliderNumber value={s.years} min={1} max={50} onChange={v => set({ years: Math.round(v) })} suffix="yrs" />
              <div className="mt-2 flex gap-1.5">{[1, 3, 5, 10, 20, 30].map(y => (
                <button key={y} onClick={() => set({ years: y })} className={`rounded-md px-2 py-1 text-[11px] ${s.years === y ? 'bg-accent text-white' : 'bg-panel-2 text-muted'}`}>{y}y</button>
              ))}</div>
            </Field>
            <Field label="Financial goal (optional)" tip="The simulator reports the share of scenarios that end at or above this value.">
              <div className="w-48"><NumberInput value={s.goal ?? 0} min={0} step={5000} prefix="$" onChange={v => set({ goal: v || null })} /></div>
            </Field>
          </div>
        </Card>

        <Card title="3 · Assumptions" right={<button onClick={() => setAdv(a => !a)} className="inline-flex items-center gap-1 text-[12px] text-accent">{adv ? 'Hide' : 'Show'} advanced <ChevronDown size={14} className={adv ? 'rotate-180' : ''} /></button>}>
          <div className="space-y-5">
            <Field label="Simulation method" tip="Parametric: correlated random returns using historical mean and covariance. Bootstrap: replays real historical months in blocks (keeps fat tails). Custom: your own return and volatility guesses.">
              <Segmented value={s.method} onChange={v => set({ method: v })}
                options={[{ value: 'parametric', label: 'Parametric' }, { value: 'bootstrap', label: 'Historical bootstrap' }, { value: 'custom', label: 'Custom assumptions' }]} />
            </Field>
            {s.method === 'custom' && (
              <div className="rounded-xl border border-warn/40 bg-warn/5 p-3">
                <div className="mb-2 text-[12px] text-warn">Your assumptions, not a market forecast. Blank fields fall back to historical estimates.</div>
                {holdings.map((h, i) => (
                  <div key={h.ticker} className="mb-2 grid grid-cols-[70px_1fr_1fr] items-center gap-2">
                    <span className="num text-[13px]">{h.ticker}</span>
                    <NumberInput value={h.customMu != null ? +(h.customMu * 100).toFixed(2) : NaN} step={0.5} suffix="% ret" onChange={v => setHoldings(holdings.map((x, j) => j === i ? { ...x, customMu: v / 100 } : x))} />
                    <NumberInput value={h.customSigma != null ? +(h.customSigma * 100).toFixed(2) : NaN} min={0} step={1} suffix="% vol" onChange={v => setHoldings(holdings.map((x, j) => j === i ? { ...x, customSigma: v / 100 } : x))} />
                  </div>
                ))}
              </div>
            )}
            <Field label="Number of simulations">
              <div className="flex flex-wrap items-center gap-2">
                {[100, 500, 1000, 5000, 10000].map(n => (
                  <button key={n} onClick={() => set({ nSims: n })} className={`num rounded-md px-2.5 py-1.5 text-[12px] ${s.nSims === n ? 'bg-accent text-white' : 'bg-panel-2 text-muted'}`}>{n.toLocaleString()}</button>
                ))}
                <div className="w-28"><NumberInput value={s.nSims} min={10} max={20000} step={100} onChange={v => set({ nSims: Math.round(v) })} /></div>
              </div>
            </Field>
            <Field label="Historical calibration window" tip="Short windows reflect recent conditions but are noisy and can extrapolate a hot streak; long windows include more market cycles but older regimes may matter less.">
              <Segmented value={s.window} onChange={v => set({ window: v })}
                options={(['1y', '3y', '5y', '10y', '20y', 'max'] as const).map(w => ({ value: w, label: w }))} />
            </Field>
            {adv && (
              <div className="grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
                <Field label="Rebalancing" tip="Bringing weights back to target. 'Never' lets winners grow into larger positions.">
                  <select className={inputCls} value={s.rebalance} onChange={e => set({ rebalance: e.target.value as Settings['rebalance'] })}>
                    {['never', 'monthly', 'quarterly', 'semiannual', 'annual'].map(r => <option key={r}>{r}</option>)}
                  </select>
                </Field>
                <Field label="Contribution timing"><Segmented value={s.contributionTiming} onChange={v => set({ contributionTiming: v })} options={[{ value: 'start', label: 'Start of period' }, { value: 'end', label: 'End' }]} /></Field>
                <Field label="Annual inflation" tip="Used to show values in today's dollars."><NumberInput value={+(s.inflation * 100).toFixed(2)} step={0.25} suffix="%" onChange={v => set({ inflation: v / 100 })} /></Field>
                <Field label="Annual fees / expense ratio" tip="Deducted monthly from the portfolio."><NumberInput value={+(s.fee * 100).toFixed(3)} min={0} max={5} step={0.05} suffix="%" onChange={v => set({ fee: v / 100 })} /></Field>
                <Field label="Dividends" tip="Prices are total-return adjusted. Turning reinvestment off pays dividends out as cash that stops compounding.">
                  <Segmented value={s.drip ? 'y' : 'n'} onChange={v => set({ drip: v === 'y' })} options={[{ value: 'y', label: 'Reinvest' }, { value: 'n', label: 'Take as cash' }]} />
                </Field>
                <Field label="Random seed" tip="Same seed + same inputs = identical results."><NumberInput value={s.seed} min={0} step={1} onChange={v => set({ seed: Math.round(v) })} /></Field>
                {s.method === 'bootstrap' && <Field label="Bootstrap block length"><NumberInput value={s.blockMonths} min={1} max={36} suffix="months" onChange={v => set({ blockMonths: Math.round(v) })} /></Field>}
                <Field label="Volatility multiplier (what-if)" tip="Scale the return volatility up or down, e.g. 1.5 = 50% more volatile markets."><NumberInput value={s.volMult} min={0.25} max={3} step={0.25} suffix="×" onChange={v => set({ volMult: v })} /></Field>
              </div>
            )}
          </div>
        </Card>
      </div>

      <DataQuality />

      <div className="sticky bottom-4 mt-6 flex flex-wrap items-center justify-end gap-2 rounded-2xl border border-line bg-panel/90 p-3 backdrop-blur">
        <Button variant="ghost" onClick={() => { navigator.clipboard?.writeText(shareUrl(holdings, settings)); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>
          <Share2 size={14} />{copied ? 'Link copied' : 'Copy share link'}
        </Button>
        <Button disabled={Math.abs(total - 100) >= 0.01 || !holdings.length} onClick={() => nav('/simulate?run=1')}><Play size={14} />Run Monte Carlo</Button>
      </div>
    </div>
  )
}

function DataQuality() {
  const { holdings, settings } = useStore()
  const [q, setQ] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const tickers = holdings.map(h => h.ticker).join(',')
  useEffect(() => {
    if (!tickers) return
    setLoading(true); setErr(null)
    const t = setTimeout(() => api.quality(tickers.split(','), settings.window).then(setQ).catch(e => setErr(e.message)).finally(() => setLoading(false)), 400)
    return () => clearTimeout(t)
  }, [tickers, settings.window])
  const cal = q?.calibration
  return (
    <Card className="mt-5" title="Data quality & historical assumptions" subtitle="Where the numbers come from, and what the past implies. These calibrate the simulation; they are not predictions."
      right={loading && <Spinner label="Checking data…" />}>
      {err && <Alert tone="loss">{err}</Alert>}
      {q && (
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead className="text-left text-faint"><tr><th className="py-1.5">Ticker</th><th>Source</th><th>History</th><th className="text-right">Obs.</th><th className="text-right">Gaps</th></tr></thead>
              <tbody>
                {q.assets.map((a: any) => (
                  <tr key={a.ticker} className="border-t border-line align-top">
                    <td className="num py-2 font-semibold">{a.ticker}</td>
                    <td className={a.synthetic ? 'text-warn' : 'text-muted'}>{a.source}<div className="text-[10px] text-faint">{a.last_updated?.slice(0, 16).replace('T', ' ')}</div></td>
                    <td className="num text-muted">{a.first_date ?? '—'} → {a.last_date ?? '—'}{a.warnings.map((w: string) => <div key={w} className="font-sans text-[11px] text-warn">{w}</div>)}</td>
                    <td className="num text-right">{a.observations?.toLocaleString() ?? '—'}</td>
                    <td className="num text-right">{a.missing_business_days_pct != null ? `${a.missing_business_days_pct}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-faint">Gaps count business days with no price. About 3–4% is normal (market holidays). Missing prices are never filled with invented values.</p>
          </div>
          <div>
            {cal?.error ? <Alert tone="loss">{cal.error}</Alert> : cal && (
              <>
                <div className="mb-2 text-[12px] text-muted">Calibration: <span className="num">{cal.start} → {cal.end}</span> · {cal.months} monthly returns</div>
                {cal.warnings?.map((w: string) => <div key={w} className="mb-2"><Alert>{w}</Alert></div>)}
                <table className="w-full text-[12px]">
                  <thead className="text-left text-faint"><tr><th className="py-1.5">Asset</th><th className="text-right">Avg annual return*</th><th className="text-right">Compound (geometric)</th><th className="text-right">Volatility</th></tr></thead>
                  <tbody>{cal.assets.map((t: string, i: number) => (
                    <tr key={t} className="border-t border-line"><td className="num py-1.5">{t}</td>
                      <td className="num text-right">{pct(cal.arithmetic_mean[i])}</td><td className="num text-right">{pct(cal.geometric_mean[i])}</td><td className="num text-right">{pct(cal.volatility[i])}</td></tr>
                  ))}</tbody>
                </table>
                <p className="mt-2 text-[11px] text-faint">*Arithmetic mean. The compound rate is lower whenever returns are volatile (volatility drag). Past averages from a strong period can overstate future returns.</p>
              </>
            )}
          </div>
        </div>
      )}
    </Card>
  )
}
