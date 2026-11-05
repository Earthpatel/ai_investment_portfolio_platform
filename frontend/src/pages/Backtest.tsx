import { useMemo, useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend as RLegend } from 'recharts'
import { Play } from 'lucide-react'
import { api } from '../lib/api'
import { toRequest, useStore } from '../lib/store'
import { num, pct, usd, usdShort } from '../lib/format'
import { Alert, Button, CHART, Card, Field, NumberInput, PageHeader, Segmented, Spinner, inputCls } from '../components/ui'

export default function Backtest() {
  const { holdings, settings } = useStore()
  const [start, setStart] = useState('2015-01-01')
  const [reb, setReb] = useState('quarterly')
  const [cost, setCost] = useState(5)
  const [res, setRes] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const run = async () => {
    setBusy(true); setErr(null)
    try { setRes(await api.backtest({ holdings: toRequest(holdings, settings).holdings, start, rebalance: reb, cost_bps: cost, initial: settings.initial || 10000 })) }
    catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  const keys = res ? Object.keys(res.strategies) : []
  const merge = (field: 'series' | 'drawdown') => {
    if (!res) return []
    const map: Record<string, any> = {}
    for (const k of keys) for (const [d, v] of res.strategies[k][field]) (map[d] ??= { date: d })[k] = v
    return Object.values(map).sort((a: any, b: any) => a.date.localeCompare(b.date))
  }
  const values = useMemo(() => merge('series'), [res]) // eslint-disable-line react-hooks/exhaustive-deps
  const dds = useMemo(() => merge('drawdown'), [res]) // eslint-disable-line react-hooks/exhaustive-deps
  const annual = useMemo(() => {
    if (!res) return []
    const years = Object.keys(res.strategies[keys[0]].metrics.annual_returns)
    return years.map(y => ({ year: y, ...Object.fromEntries(keys.map(k => [k, res.strategies[k].metrics.annual_returns[y]])) }))
  }, [res]) // eslint-disable-line react-hooks/exhaustive-deps
  const color = (i: number, k: string) => k === 'benchmark' ? '#94a3b8' : CHART.series[i]

  return (
    <div>
      <PageHeader eyebrow="Analytics" title="Backtesting">
        What would have happened if you had held this portfolio in the past? One real historical path, versus Monte Carlo’s many possible futures. Every strategy uses only information available on each date.
      </PageHeader>
      <Card title="Settings" right={<Button onClick={run} disabled={busy}>{busy ? <Spinner /> : <Play size={14} />}Run backtest</Button>}>
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Start date" hint="The test begins once every asset has data."><input type="date" className={inputCls} value={start} onChange={e => setStart(e.target.value)} /></Field>
          <Field label="Rebalancing"><Segmented value={reb} onChange={setReb} options={['monthly', 'quarterly', 'annual'].map(v => ({ value: v, label: v }))} /></Field>
          <Field label="Transaction cost" tip="Charged on the value traded at each rebalance (basis points: 10 bps = 0.10%)."><NumberInput value={cost} min={0} max={200} suffix="bps" onChange={setCost} /></Field>
        </div>
      </Card>
      {err && <div className="mt-4"><Alert tone="loss">{err}</Alert></div>}
      {res && (
        <div className="mt-5 space-y-5">
          {res.synthetic && <Alert>Synthetic development data.</Alert>}
          <Card title={`Growth of ${usd(settings.initial || 10000)}`} subtitle={`${res.start} → ${res.end}`}>
            <div className="h-80">
              <ResponsiveContainer>
                <LineChart data={values}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="date" minTickGap={60} /><YAxis width={56} tickFormatter={usdShort} /><Tooltip formatter={(v) => usd(Number(v))} /><RLegend />
                  {keys.map((k, i) => <Line key={k} dataKey={k} name={res.strategies[k].label} stroke={color(i, k)} strokeDasharray={k === 'benchmark' ? '5 4' : undefined} dot={false} strokeWidth={k === 'buy_and_hold' ? 2.2 : 1.5} isAnimationActive={false} connectNulls />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title="Metrics">
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead className="text-left text-faint"><tr><th className="py-1.5">Strategy</th><th className="text-right">Total</th><th className="text-right">CAGR</th><th className="text-right">Volatility</th><th className="text-right">Sharpe</th><th className="text-right">Sortino</th><th className="text-right">Max DD</th><th className="text-right">Rebalances</th><th className="text-right">Turnover</th><th className="text-right">Costs paid</th></tr></thead>
                <tbody>{keys.map((k, i) => { const s = res.strategies[k], m = s.metrics; return (
                  <tr key={k} className="border-t border-line"><td className="py-2"><span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: color(i, k) }} />{s.label}</td>
                    <td className="num text-right">{pct(m.total_return, 0)}</td><td className="num text-right">{pct(m.cagr)}</td><td className="num text-right">{pct(m.volatility)}</td><td className="num text-right">{num(m.sharpe)}</td><td className="num text-right">{num(m.sortino)}</td>
                    <td className="num text-right text-loss">{pct(m.max_drawdown)}</td><td className="num text-right">{s.trading?.rebalances ?? '—'}</td><td className="num text-right">{s.trading ? `${s.trading.turnover.toFixed(1)}×` : '—'}</td><td className="num text-right">{s.trading ? usd(s.trading.costs_paid) : '—'}</td></tr>) })}</tbody>
              </table>
            </div>
          </Card>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Drawdowns">
              <div className="h-64"><ResponsiveContainer>
                <AreaChart data={dds}><XAxis dataKey="date" minTickGap={60} /><YAxis width={44} reversed tickFormatter={v => pct(-Number(v), 0)} /><Tooltip formatter={(v) => pct(-Number(v))} />
                  {keys.map((k, i) => <Area key={k} dataKey={k} name={res.strategies[k].label} stroke={color(i, k)} fill={color(i, k)} fillOpacity={0.06} isAnimationActive={false} connectNulls />)}
                </AreaChart></ResponsiveContainer></div>
            </Card>
            <Card title="Calendar-year returns">
              <div className="h-64"><ResponsiveContainer>
                <BarChart data={annual}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="year" /><YAxis width={44} tickFormatter={v => pct(v, 0)} /><Tooltip formatter={(v) => pct(Number(v))} />
                  {keys.map((k, i) => <Bar key={k} dataKey={k} name={res.strategies[k].label} fill={color(i, k)} isAnimationActive={false} />)}
                </BarChart></ResponsiveContainer></div>
            </Card>
          </div>
          <Card title="Read before drawing conclusions" tone="warn">
            <ul className="space-y-1.5 text-[13px] text-muted">{res.disclosures.map((d: string) => <li key={d}>• {d}</li>)}</ul>
          </Card>
        </div>
      )}
    </div>
  )
}
