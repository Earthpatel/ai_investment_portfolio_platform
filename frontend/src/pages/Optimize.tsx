import { useState } from 'react'
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis, Legend as RLegend } from 'recharts'
import { Check, Play } from 'lucide-react'
import { api } from '../lib/api'
import { toRequest, useStore } from '../lib/store'
import { num, pct } from '../lib/format'
import { Alert, Button, CHART, Card, Field, NumberInput, PageHeader, Segmented, Spinner } from '../components/ui'

const LABELS: Record<string, string> = { current: 'Your portfolio', equal_weight: 'Equal weight', min_variance: 'Minimum variance', max_sharpe: 'Max Sharpe (mean-variance)', risk_parity: 'Risk parity', target_volatility: 'Target volatility' }
const COLORS: Record<string, string> = { current: '#f8fafc', equal_weight: CHART.series[7], min_variance: CHART.series[1], max_sharpe: CHART.series[2], risk_parity: CHART.series[3], target_volatility: CHART.series[5] }

export default function Optimize() {
  const { holdings, settings, setHoldings } = useStore()
  const [window, setWindow] = useState('5y')
  const [maxW, setMaxW] = useState(40)
  const [secCap, setSecCap] = useState(100)
  const [tv, setTv] = useState(0)
  const [rf, setRf] = useState(3)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const run = async () => {
    setBusy(true); setErr(null)
    try {
      setRes(await api.optimize({ holdings: toRequest(holdings, settings).holdings, window, rf: rf / 100, max_weight: maxW / 100, sector_cap: secCap < 100 ? secCap / 100 : null, target_vol: tv > 0 ? tv / 100 : null }))
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const apply = (w: number[]) => setHoldings(res.tickers.map((t: string, i: number) => ({ ticker: t, weight: +(w[i] * 100).toFixed(2) })).filter((h: any) => h.weight > 0.01))

  return (
    <div>
      <PageHeader eyebrow="Analytics" title="Portfolio Optimization">
        Optimizers search for weights that balance return and risk using historical estimates. They are very sensitive to the expected-return estimate, so treat the results as a starting point, not an answer.
      </PageHeader>
      <Card title="Constraints" right={<Button onClick={run} disabled={busy || holdings.length < 2}>{busy ? <Spinner /> : <Play size={14} />}Optimize</Button>}>
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
          <Field label="Estimation window"><Segmented value={window} onChange={setWindow} options={['3y', '5y', '10y', 'max'].map(v => ({ value: v, label: v }))} /></Field>
          <Field label="Max per asset" tip="No single asset may exceed this weight (long-only: no shorting)."><NumberInput value={maxW} min={5} max={100} step={5} suffix="%" onChange={setMaxW} /></Field>
          <Field label="Max per sector" tip="Total weight of assets that share a GICS sector."><NumberInput value={secCap} min={10} max={100} step={5} suffix="%" onChange={setSecCap} /></Field>
          <Field label="Target volatility" tip="0 = off. Highest expected return with volatility at or below this."><NumberInput value={tv} min={0} max={80} step={1} suffix="%" onChange={setTv} /></Field>
          <Field label="Risk-free rate"><NumberInput value={rf} min={0} max={15} step={0.25} suffix="%" onChange={setRf} /></Field>
        </div>
        {holdings.length < 2 && <div className="mt-3"><Alert>Add at least two assets in the Portfolio Builder.</Alert></div>}
      </Card>
      {err && <div className="mt-4"><Alert tone="loss">{err}</Alert></div>}
      {res && (
        <div className="mt-5 space-y-5">
          {res.synthetic && <Alert>Synthetic development data.</Alert>}
          {[...res.notes, ...res.warnings].map((n: string) => <Alert key={n}>{n}</Alert>)}
          <div className="grid gap-5 xl:grid-cols-[1.3fr_1fr]">
            <Card title="Efficient frontier" subtitle={`Each grey dot is a random portfolio of your assets; the blue curve is the lowest risk for each level of return. Estimated from ${res.period[0]} → ${res.period[1]}.`}>
              <div className="h-96">
                <ResponsiveContainer>
                  <ScatterChart margin={{ left: 8, right: 8 }}>
                    <CartesianGrid stroke={CHART.grid} />
                    <XAxis type="number" dataKey="volatility" name="Volatility" tickFormatter={v => pct(v, 0)} domain={['auto', 'auto']} label={{ value: 'Volatility (risk)', position: 'insideBottom', offset: -2, fill: 'var(--muted)', fontSize: 11 }} />
                    <YAxis type="number" dataKey="expected_return" name="Expected return" tickFormatter={v => pct(v, 0)} width={48} domain={['auto', 'auto']} />
                    <ZAxis range={[14, 14]} />
                    <Tooltip formatter={(v) => pct(Number(v))} />
                    <RLegend />
                    <Scatter name="Random portfolios" data={res.random} fill="var(--faint)" fillOpacity={0.35} isAnimationActive={false} />
                    <Scatter name="Efficient frontier" data={res.frontier} fill="var(--accent)" line={{ stroke: 'var(--accent)', strokeWidth: 2 }} isAnimationActive={false} />
                    <Scatter name="Single assets" data={res.assets} fill="var(--warn)" shape="diamond" isAnimationActive={false} />
                    {Object.entries<any>(res.portfolios).map(([k, p]) => <Scatter key={k} name={LABELS[k]} data={[p]} fill={COLORS[k]} shape={k === 'current' ? 'star' : 'circle'} isAnimationActive={false}><ZAxis range={[120, 120]} /></Scatter>)}
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title="Correlation heatmap" subtitle="How the assets moved together (monthly). Lower correlation means more diversification.">
              <Heatmap labels={res.tickers} m={res.correlation} />
            </Card>
          </div>
          <Card title="Strategies compared" subtitle="Expected return and volatility are historical estimates. The equal-weight reference ignores the caps.">
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead className="text-left text-faint"><tr><th className="py-1.5">Strategy</th><th className="text-right">Exp. return</th><th className="text-right">Volatility</th><th className="text-right">Sharpe</th>{res.tickers.map((t: string) => <th key={t} className="num text-right">{t}</th>)}<th></th></tr></thead>
                <tbody>{Object.entries<any>(res.portfolios).map(([k, p]) => (
                  <tr key={k} className="border-t border-line">
                    <td className="py-2"><span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: COLORS[k] }} />{LABELS[k]}</td>
                    <td className="num text-right">{pct(p.expected_return)}</td><td className="num text-right">{pct(p.volatility)}</td><td className="num text-right">{num(p.sharpe)}</td>
                    {p.weights.map((w: number, i: number) => <td key={i} className={`num text-right ${w < 0.005 ? 'text-faint' : ''}`}>{pct(w, 0)}</td>)}
                    <td className="text-right">{k !== 'current' && <button onClick={() => apply(p.weights)} className="inline-flex items-center gap-1 rounded-md bg-panel-2 px-2 py-1 text-[11px] hover:text-accent"><Check size={12} />Use</button>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </Card>
          <Card title="How stable are the ‘optimal’ weights?" subtitle={`Max-Sharpe re-optimized on ${res.sensitivity.resamples} bootstrap resamples of the same history. Wide bars mean small changes in the data flip the answer, a classic weakness of mean-variance optimization.`} tone="warn">
            <div className="space-y-2">
              {res.tickers.map((t: string, i: number) => (
                <div key={t} className="grid grid-cols-[60px_1fr_120px] items-center gap-3 text-[12px]">
                  <span className="num">{t}</span>
                  <div className="relative h-3 rounded-full bg-panel-2">
                    <div className="absolute h-3 rounded-full bg-warn/40" style={{ left: `${res.sensitivity.p10[i] * 100}%`, width: `${Math.max(0.8, (res.sensitivity.p90[i] - res.sensitivity.p10[i]) * 100)}%` }} />
                    <div className="absolute top-[-2px] h-4 w-0.5 bg-ink" style={{ left: `${res.portfolios.max_sharpe.weights[i] * 100}%` }} />
                  </div>
                  <span className="num text-faint">{pct(res.sensitivity.p10[i], 0)} – {pct(res.sensitivity.p90[i], 0)}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

function Heatmap({ labels, m }: { labels: string[]; m: number[][] }) {
  const color = (v: number) => v >= 0 ? `rgba(248,113,113,${0.12 + v * 0.75})` : `rgba(52,211,153,${0.12 - v * 0.75})`
  return (
    <div className="overflow-x-auto">
      <table className="mx-auto text-[11px]">
        <thead><tr><th></th>{labels.map(l => <th key={l} className="num px-1 pb-1 font-medium text-muted">{l}</th>)}</tr></thead>
        <tbody>{m.map((row, i) => (
          <tr key={i}><th className="num pr-2 text-right font-medium text-muted">{labels[i]}</th>
            {row.map((v, j) => <td key={j} className="num h-10 w-12 text-center" style={{ background: color(v) }} title={`${labels[i]} / ${labels[j]}: ${v.toFixed(2)}`}>{v.toFixed(2)}</td>)}
          </tr>
        ))}</tbody>
      </table>
      <p className="mt-2 text-center text-[11px] text-faint">Red = move together · Green = move oppositely</p>
    </div>
  )
}
