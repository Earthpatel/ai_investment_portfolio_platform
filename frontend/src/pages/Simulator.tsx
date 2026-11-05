import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Download, FastForward, Image, Pause, Play, RotateCcw, Save, Snail, FileText } from 'lucide-react'
import { api, type SimResult } from '../lib/api'
import { configKey, toRequest, useStore } from '../lib/store'
import { downloadText, histogram, pct, signedPct, usd, usdShort } from '../lib/format'
import { FanChart, type FanChartHandle } from '../components/FanChart'
import { AllocationDonut, Legend } from '../components/shared'
import { Alert, Button, CHART, Card, PageHeader, Segmented, Spinner, Stat } from '../components/ui'

export default function Simulator() {
  const store = useStore()
  const { holdings, settings, result, setResult, resultKey, setResultKey, saved, setSaved } = store
  const [params, setParams] = useSearchParams()
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [revealed, setRevealed] = useState(0)
  const [running, setRunning] = useState(false)
  const [speed, setSpeed] = useState(30) // paths per second
  const [real, setReal] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const chart = useRef<FanChartHandle>(null)
  const K = result?.sample_paths.length ?? 0
  const complete = !!result && revealed >= K
  const key = configKey(holdings, settings)
  const stale = !!result && resultKey !== key

  const run = useCallback(async () => {
    abort.current?.abort()
    const ac = new AbortController(); abort.current = ac
    setLoading(true); setErr(null); setRunning(false); setRevealed(0)
    try {
      const r = await api.simulate(toRequest(holdings, settings), ac.signal)
      setResult(r); setResultKey(configKey(holdings, settings)); setRevealed(0); setRunning(true)
    } catch (e: any) {
      if (e.name !== 'AbortError') setErr(e.message)
    } finally { setLoading(false) }
  }, [holdings, settings, setResult, setResultKey])

  useEffect(() => {
    if (params.get('run') === '1') { params.delete('run'); setParams(params, { replace: true }); run() }
    else if (result && !stale) setRevealed(result.sample_paths.length) // returning to the page: show the finished run
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Animation loop: reveal paths at `speed` paths/sec
  useEffect(() => {
    if (!running || !result) return
    let last = performance.now(), id = 0
    const tick = (now: number) => {
      const dt = Math.max(0, (now - last) / 1000); last = now
      setRevealed(r => {
        const nr = Math.min(K, r + dt * speed)
        if (nr >= K) setRunning(false)
        return nr
      })
      id = requestAnimationFrame(tick)
    }
    id = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(id)
  }, [running, speed, result, K])

  const N = result?.terminal.length ?? 0
  const simsDone = !result ? 0 : complete ? N : Math.floor((revealed / K) * N)

  return (
    <div>
      <PageHeader eyebrow="Step 4–6" title="Monte Carlo Simulator">
        Each line is one possible future for your portfolio, built from random monthly returns. Watch the spread widen: uncertainty compounds with time.
      </PageHeader>

      {err && <div className="mb-4"><Alert tone="loss">{err}</Alert></div>}
      {stale && <div className="mb-4"><Alert>Your portfolio or settings changed since this run, so these results describe the <b>previous</b> inputs. Run again to update.</Alert></div>}

      <Card className="mb-5"
        title={<span className="flex items-center gap-2">Simulated portfolio paths {result && <span className="num rounded-md bg-panel-2 px-2 py-0.5 text-[12px] font-normal text-muted">{simsDone.toLocaleString()} / {N.toLocaleString()} simulations</span>}</span>}
        subtitle={result ? `${result.assumptions.label} · ${holdings.length} assets · ${settings.years} years · seed ${settings.seed}` : 'Configure your portfolio in the Builder, then run.'}
        right={
          <div className="flex flex-wrap items-center gap-2">
            {!running && (!result || complete) && <Button onClick={run} disabled={loading}>{loading ? <Spinner /> : <Play size={14} />}{result ? 'Run again' : 'Start'}</Button>}
            {running && <Button variant="ghost" onClick={() => setRunning(false)}><Pause size={14} />Pause</Button>}
            {!running && result && !complete && <Button onClick={() => setRunning(true)}><Play size={14} />Resume</Button>}
            {result && <Button variant="ghost" onClick={() => { setRunning(false); setRevealed(0) }}><RotateCcw size={14} />Reset</Button>}
            {loading && <Button variant="danger" onClick={() => abort.current?.abort()}>Cancel</Button>}
          </div>}>
        <div className="mb-4 flex flex-wrap items-center gap-4 text-[12px]">
          <div className="flex items-center gap-2">
            <button onClick={() => setSpeed(2)} title="Slow motion" className={`rounded-md p-1.5 ${speed <= 2 ? 'bg-accent text-white' : 'bg-panel-2 text-muted'}`}><Snail size={14} /></button>
            <span className="text-muted">Speed</span>
            <input type="range" min={0} max={100} value={Math.round(Math.log(speed) / Math.log(600) * 100)} aria-label="Simulation speed"
              onChange={e => setSpeed(Math.max(1, Math.round(Math.pow(600, +e.target.value / 100))))} className="w-40" />
            <span className="num w-20 text-faint">{speed} paths/s</span>
            <button onClick={() => { setRevealed(K); setRunning(false) }} title="Maximum speed: finish now" className="rounded-md bg-panel-2 p-1.5 text-muted hover:text-ink"><FastForward size={14} /></button>
          </div>
          <Segmented size="sm" value={real ? 'r' : 'n'} onChange={v => setReal(v === 'r')} options={[{ value: 'n', label: 'Nominal $' }, { value: 'r', label: 'Inflation-adjusted' }]} />
          <div className="flex flex-wrap gap-3 text-faint">
            <span className="inline-flex items-center gap-1"><i className="h-0.5 w-4 bg-accent" />paths ({K} of {N} drawn)</span>
            <span className="inline-flex items-center gap-1"><i className="h-0.5 w-4 bg-ink" />median</span>
            <span className="inline-flex items-center gap-1"><i className="h-2 w-4 rounded-sm bg-accent/30" />25–75th / 10–90th</span>
            <span className="inline-flex items-center gap-1"><i className="h-0.5 w-4 border-t-2 border-dashed border-warn" />contributed</span>
          </div>
        </div>
        {result ? <FanChart ref={chart} result={result} revealed={revealed} complete={complete} real={real} goal={settings.goal} />
          : <div className="grid h-[420px] place-items-center rounded-xl border border-dashed border-line text-[13px] text-faint">
            {loading ? <Spinner label="Running simulations…" /> : <span>Press <b>Start</b> to simulate {settings.nSims.toLocaleString()} futures. <Link to="/builder" className="text-accent">Edit portfolio →</Link></span>}
          </div>}
        {result && !complete && <p className="mt-2 text-[12px] text-faint">Percentile bands appear when all paths are drawn. The live counters below already use every completed simulation.</p>}
      </Card>

      {result && <Live result={result} simsDone={simsDone} goal={settings.goal} />}
      {result && complete && <Dashboard result={result} real={real} chart={chart}
        onSave={() => setSaved([...saved.filter(x => x.name !== `Scenario ${String.fromCharCode(65 + saved.length)}`), { name: `Scenario ${String.fromCharCode(65 + Math.min(saved.length, 25))}`, holdings, settings }].slice(-4))} />}
    </div>
  )
}

function Live({ result, simsDone, goal }: { result: SimResult; simsDone: number; goal: number | null }) {
  const total = result.summary.total_contributed
  const t = result.terminal
  const hist = useMemo(() => {
    const s = [...t].sort((a, b) => a - b)
    const lo = s[Math.floor(s.length * 0.005)], hi = s[Math.floor(s.length * 0.99)]
    return histogram(t.slice(0, Math.max(1, simsDone)), 36, lo, hi).map(b => ({ x: b.mid, count: b.count }))
  }, [t, Math.round(simsDone / Math.max(1, t.length / 120))]) // eslint-disable-line react-hooks/exhaustive-deps
  const conv = useMemo(() => {
    const out: { n: number; below: number; goal: number | null }[] = []
    let below = 0, hit = 0
    const step = Math.max(1, Math.floor(t.length / 250))
    for (let i = 0; i < t.length; i++) {
      if (t[i] < total) below++
      if (goal && t[i] >= goal) hit++
      if ((i + 1) % step === 0 || i === t.length - 1) out.push({ n: i + 1, below: below / (i + 1), goal: goal ? hit / (i + 1) : null })
    }
    return out
  }, [t, total, goal])
  const convShown = conv.filter(c => c.n <= simsDone)
  const cur = convShown[convShown.length - 1]
  return (
    <div className="mb-5 grid gap-5 lg:grid-cols-2">
      <Card title="Ending wealth distribution" subtitle="Where each finished simulation landed. It builds as simulations complete.">
        <div className="h-60">
          <ResponsiveContainer>
            <BarChart data={hist} margin={{ left: 4, right: 8 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="x" tickFormatter={usdShort} minTickGap={30} />
              <YAxis width={36} />
              <Tooltip formatter={(v) => [v, 'simulations']} labelFormatter={(l) => `≈ ${usd(Number(l))}`} />
              <Bar dataKey="count" fill="var(--accent)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
              <ReferenceLine x={hist.reduce((b, h) => Math.abs(h.x - total) < Math.abs(b - total) ? h.x : b, hist[0]?.x ?? 0)} stroke="var(--warn)" strokeDasharray="4 3" label={{ value: 'contributed', fill: 'var(--warn)', fontSize: 11, position: 'top' }} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Convergence" subtitle="The estimated probability settles down as more simulations are added. Monte Carlo's core idea: more trials, less noise.">
        <div className="mb-2 flex gap-4 text-[12px]">
          <span>P(end below contributions): <b className="num text-loss">{cur ? pct(cur.below) : '—'}</b></span>
          {goal ? <span>P(reach {usdShort(goal)}): <b className="num text-ai">{cur?.goal != null ? pct(cur.goal) : '—'}</b></span> : null}
        </div>
        <div className="h-52">
          <ResponsiveContainer>
            <LineChart data={convShown} margin={{ left: 4, right: 8 }}>
              <CartesianGrid stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="n" type="number" domain={[0, t.length]} tickFormatter={v => v.toLocaleString()} />
              <YAxis width={44} domain={[0, 1]} tickFormatter={v => pct(v, 0)} />
              <Tooltip formatter={(v) => pct(Number(v))} labelFormatter={l => `after ${(Number(l)).toLocaleString()} sims`} />
              <Line dataKey="below" name="P(below contributions)" stroke="var(--loss)" dot={false} isAnimationActive={false} strokeWidth={2} />
              {goal && <Line dataKey="goal" name="P(goal)" stroke="var(--ai)" dot={false} isAnimationActive={false} strokeWidth={2} />}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  )
}

function Dashboard({ result, real, chart, onSave }: { result: SimResult; real: boolean; chart: React.RefObject<FanChartHandle | null>; onSave: () => void }) {
  const { settings, holdings } = useStore()
  const s = result.summary
  const [goal, setGoal] = useState(settings.goal ?? Math.round(s.median_end / 1000) * 1000)
  const terms = real ? result.terminal_real : result.terminal
  const goalProb = terms.filter(v => v >= goal).length / terms.length
  const ddHist = useMemo(() => histogram(result.max_drawdowns, 25, 0, Math.max(...result.max_drawdowns)).map(b => ({ x: b.mid, count: b.count })), [result])
  const P = real ? result.percentiles_real : result.percentiles
  const yearly = result.yearly.map(y => {
    const i = Math.round(y.year * 12)
    return { year: y.year, contributed: real ? y.contributed / result.inflation_factor[i] : y.contributed, p10: P['10'][i], p25: P['25'][i], p50: P['50'][i], p75: P['75'][i], p90: P['90'][i] }
  })

  const exportCSV = () => {
    const head = 'year,contributed,p5,p10,p25,median,p75,p90,p95,median_inflation_adjusted\n'
    const rows = result.yearly.map(y => [y.year, y.contributed, y.p5, y.p10, y.p25, y.p50, y.p75, y.p90, y.p95, y.median_real].map(v => (Number(v)).toFixed(2)).join(',')).join('\n')
    downloadText(`simulation_${result.request_hash}.csv`, head + rows, 'text/csv')
  }
  const exportPNG = () => {
    const url = chart.current?.toPNG(); if (!url) return
    const a = document.createElement('a'); a.href = url; a.download = `fan_chart_${result.request_hash}.png`; a.click()
  }
  const exportReport = () => {
    const a = result.assumptions
    const md = `# Monte Carlo simulation report\n\nGenerated ${new Date().toISOString()} · run id ${result.request_hash}${result.synthetic ? '\n\n**DEVELOPMENT MODE: synthetic prices, not market data.**' : ''}\n\n` +
      `## Portfolio\n${a.tickers.map((t, i) => `- ${t}: ${(a.weights[i] * 100).toFixed(1)}%`).join('\n')}\n\n` +
      `## Inputs\n- Initial: ${usd(settings.initial)}; contributions: ${settings.contributionFreq === 'none' ? 'none' : `${usd(settings.contribution)} ${settings.contributionFreq} (${settings.contributionTiming})`}\n- Horizon: ${settings.years} years; simulations: ${s.n_sims}; seed: ${settings.seed}\n- Method: ${a.label}\n- Rebalancing: ${settings.rebalance}; fees: ${pct(settings.fee, 2)}/yr; inflation: ${pct(settings.inflation, 2)}; dividends: ${settings.drip ? 'reinvested' : 'paid as cash'}\n- Calibration data: ${a.calibration_start} → ${a.calibration_end} (${a.calibration_months} months)\n\n` +
      `## Assumed annual return / volatility\n${a.tickers.map((t, i) => `- ${t}: arithmetic ${pct(a.arithmetic_mean[i])}, geometric ${pct(a.geometric_mean[i])}, volatility ${pct(a.volatility[i])}`).join('\n')}\n\n` +
      `## Results (nominal)\n- Total contributed: ${usd(s.total_contributed)}\n- Median ending value: ${usd(s.median_end)} (10th–90th pct: ${usd(s.p10_end)} – ${usd(s.p90_end)})\n- Median ending value in today's dollars: ${usd(s.median_end_real)}\n- Probability of ending below contributions: ${pct(s.prob_below_contributions)}\n${s.prob_goal != null ? `- Probability of reaching ${usd(settings.goal)}: ${pct(s.prob_goal)}\n` : ''}- Median annualized time-weighted return: ${pct(s.median_annualized_twr)} (10th–90th: ${pct(s.p10_annualized_twr)} – ${pct(s.p90_annualized_twr)})\n- Median max drawdown: ${pct(s.median_max_drawdown)}; P(drawdown > 30%): ${pct(s.prob_drawdown_over_30)}\n- Average of worst 5% outcomes (CVaR 5%): ${usd(s.cvar5_end)}\n\n` +
      `## Notes & warnings\n${[...a.notes, ...a.warnings].map(n => `- ${n}`).join('\n')}\n\n## Limitations\n- Simulations explore possibilities under stated assumptions; they are not forecasts or guarantees.\n- Real markets can have larger crashes, changing correlations and regime shifts than the calibration window shows.\n- Taxes are ignored.\n`
    downloadText(`simulation_report_${result.request_hash}.md`, md, 'text/markdown')
  }

  return (
    <div className="space-y-5">
      {result.synthetic && <Alert>These results use synthetic development data and do not describe real markets.</Alert>}
      <Card title="Results" subtitle={`${s.n_sims.toLocaleString()} simulations · ${real ? 'inflation-adjusted (today’s $)' : 'nominal dollars'} where shown`}
        right={<div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={onSave}><Save size={14} />Save as scenario</Button>
          <Button variant="ghost" onClick={exportCSV}><Download size={14} />CSV</Button>
          <Button variant="ghost" onClick={exportPNG}><Image size={14} />PNG</Button>
          <Button variant="ghost" onClick={exportReport}><FileText size={14} />Report</Button>
        </div>}>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
          <Stat label="Total contributed" value={usd(s.total_contributed)} />
          <Stat label="Median ending value" value={usd(s.median_end)} sub={`${usd(s.median_end_real)} in today’s $`} tip="Half of the simulated futures ended above this, half below. This is the value of the median path's ending, not the result of compounding a 'median annual return'." />
          <Stat label="Median gain / loss" value={usd(s.median_gain)} tone={s.median_gain >= 0 ? 'gain' : 'loss'} sub={s.median_multiple_of_contributions ? `${s.median_multiple_of_contributions.toFixed(2)}× money put in` : undefined} />
          <Stat label="Pessimistic (10th pct)" value={usd(s.p10_end)} tone="loss" sub="1 in 10 futures ended lower" />
          <Stat label="Optimistic (90th pct)" value={usd(s.p90_end)} tone="gain" sub="1 in 10 futures ended higher" />
          <Stat label="Chance of ending below contributions" value={pct(s.prob_below_contributions)} tone={s.prob_below_contributions > 0.2 ? 'loss' : undefined} tip="Share of all simulations whose final value was less than the total money you put in." />
          <Stat label="Median annualized return" value={pct(s.median_annualized_twr)} sub={`10th–90th: ${pct(s.p10_annualized_twr)} to ${pct(s.p90_annualized_twr)}`} tip="Time-weighted: the portfolio's own growth rate, ignoring the timing of contributions. A range, not a promise." />
          <Stat label="Median worst drawdown" value={pct(s.median_max_drawdown)} tone="warn" sub={`1 in 10: worse than ${pct(s.p90_max_drawdown)}`} tip="Largest peak-to-trough fall along each simulated path." />
          <Stat label="P(drawdown > 30%)" value={pct(s.prob_drawdown_over_30)} tone="warn" />
          <Stat label="Worst-5% average (CVaR)" value={usd(s.cvar5_end)} tone="loss" tip="Average ending value across the worst 5% of simulations." />
          {s.prob_goal != null && <Stat label={`P(reach ${usdShort(settings.goal!)})`} value={pct(s.prob_goal)} tone="ai" />}
          <Stat label="Compute time" value={`${result.elapsed_ms} ms`} sub={`run ${result.request_hash}`} />
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <Card title="Year-by-year projection" subtitle="The spread of possible values at each year: shaded 10–90th and 25–75th percentile ranges.">
          <div className="h-72">
            <ResponsiveContainer>
              <ComposedChart data={yearly} margin={{ left: 8, right: 8 }}>
                <CartesianGrid stroke={CHART.grid} vertical={false} />
                <XAxis dataKey="year" tickFormatter={v => `${v}y`} />
                <YAxis width={56} tickFormatter={usdShort} />
                <Tooltip formatter={(v: any) => Array.isArray(v) ? `${usd(v[0])} – ${usd(v[1])}` : usd(Number(v))} labelFormatter={l => `Year ${l}`} />
                <Area dataKey={(d: any) => [d.p10, d.p90]} name="10–90th" fill="var(--accent)" fillOpacity={0.12} stroke="none" isAnimationActive={false} />
                <Area dataKey={(d: any) => [d.p25, d.p75]} name="25–75th" fill="var(--accent)" fillOpacity={0.25} stroke="none" isAnimationActive={false} />
                <Line dataKey="p50" name="Median" stroke="var(--text)" strokeWidth={2} dot={{ r: 2 }} />
                <Line dataKey="contributed" name="Contributed" stroke="var(--warn)" strokeDasharray="5 4" dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 max-h-56 overflow-auto">
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 bg-panel text-left text-faint"><tr><th className="py-1">Year</th><th className="text-right">Contributed</th><th className="text-right">10th</th><th className="text-right">Median</th><th className="text-right">90th</th></tr></thead>
              <tbody>{yearly.map(y => <tr key={y.year} className="num border-t border-line"><td className="py-1">{y.year}</td><td className="text-right">{usd(y.contributed)}</td><td className="text-right text-loss">{usd(y.p10)}</td><td className="text-right">{usd(y.p50)}</td><td className="text-right text-gain">{usd(y.p90)}</td></tr>)}</tbody>
            </table>
          </div>
        </Card>
        <div className="space-y-5">
          <Card title="Goal explorer" subtitle="Drag to see how likely different targets are. Computed live from every simulation." tone="ai">
            <div className="num text-3xl font-semibold text-ai">{pct(goalProb)}</div>
            <div className="text-[13px] text-muted">of futures reach at least <b className="num text-ink">{usd(goal)}</b>{real && ' (today’s $)'}</div>
            <input type="range" className="mt-3 w-full" aria-label="Goal" min={0} max={Math.round(s.p95_end * 1.1)} step={Math.max(100, Math.round(s.p95_end / 400))} value={goal} onChange={e => setGoal(+e.target.value)} />
            <p className="mt-2 text-[12px] text-faint">To see the effect of contributing more or investing longer, try the what-if buttons in <Link to="/risk" className="text-accent">Risk Analytics</Link>.</p>
          </Card>
          <Card title="Drawdown risk" subtitle="Distribution of the worst fall from a previous high in each simulated path (excluding contributions).">
            <div className="h-44">
              <ResponsiveContainer>
                <BarChart data={ddHist}><XAxis dataKey="x" tickFormatter={v => pct(v, 0)} minTickGap={24} /><YAxis width={34} /><Tooltip formatter={(v) => [v, 'simulations']} labelFormatter={l => `≈ ${pct(Number(l))} drop`} /><Bar dataKey="count" fill="var(--warn)" isAnimationActive={false} /></BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title="Allocation"><div className="grid grid-cols-[140px_1fr] items-center gap-3"><AllocationDonut holdings={holdings} size={140} /><Legend holdings={holdings} /></div></Card>
        </div>
      </div>

      <Card title="Assumptions behind these results" subtitle={result.assumptions.label}>
        <div className="grid gap-5 lg:grid-cols-2">
          <table className="w-full text-[12px]">
            <thead className="text-left text-faint"><tr><th className="py-1">Asset</th><th className="text-right">Weight</th><th className="text-right">Avg return (arith.)</th><th className="text-right">Compound</th><th className="text-right">Volatility</th></tr></thead>
            <tbody>{result.assumptions.tickers.map((t, i) => (
              <tr key={t} className="num border-t border-line"><td className="py-1.5">{t}</td><td className="text-right">{pct(result.assumptions.weights[i])}</td><td className="text-right">{signedPct(result.assumptions.arithmetic_mean[i])}</td><td className="text-right">{signedPct(result.assumptions.geometric_mean[i])}</td><td className="text-right">{pct(result.assumptions.volatility[i])}</td></tr>
            ))}</tbody>
          </table>
          <ul className="space-y-1.5 text-[12px] text-muted">
            {result.assumptions.notes.map(n => <li key={n}>• {n}</li>)}
            {result.assumptions.warnings.map(n => <li key={n} className="text-warn">⚠ {n}</li>)}
            <li>• Returns are generated monthly as log returns, so values can never go negative. Arithmetic averages exceed compound growth when volatility is high.</li>
            <li>• Limitations: extreme crashes, changing correlations and regime shifts can be larger than history in the calibration window suggests. Taxes are ignored.</li>
            <li>• Data: {result.data.map(d => `${d.ticker} (${d.source}${d.last_date ? `, to ${d.last_date}` : ''})`).join(', ')}</li>
          </ul>
        </div>
      </Card>
    </div>
  )
}
