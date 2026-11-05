import { useEffect, useMemo, useState } from 'react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend as RLegend } from 'recharts'
import { Plus } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../lib/store'
import { num, pct, usd } from '../lib/format'
import { TickerSearch } from '../components/shared'
import { Alert, Button, CHART, Card, PageHeader, Segmented, Spinner, Stat } from '../components/ui'

export default function Explorer() {
  const { holdings, setHoldings } = useStore()
  const [ticker, setTicker] = useState(holdings[0]?.ticker ?? 'SPY')
  const [period, setPeriod] = useState('5y')
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    setBusy(true); setErr(null)
    api.asset(ticker, period).then(setD).catch(e => { setErr(e.message); setD(null) }).finally(() => setBusy(false))
  }, [ticker, period])

  const compare = useMemo(() => {
    if (!d) return []
    const map: Record<string, any> = {}
    d.series.forEach((p: any) => (map[p.date] = { date: p.date, [d.meta.ticker]: p.close }))
    for (const [k, c] of Object.entries<any>(d.comparisons)) for (const [dt, v] of c.series) (map[dt] ??= { date: dt })[k] = v
    return Object.values(map).sort((a: any, b: any) => a.date.localeCompare(b.date))
  }, [d])

  const normal = useMemo(() => {
    if (!d) return []
    const { mean, std } = d.normal_ref
    const total = d.return_hist.reduce((a: number, b: any) => a + b.count, 0)
    const w = d.return_hist.length > 1 ? d.return_hist[1].x - d.return_hist[0].x : 1
    return d.return_hist.map((b: any) => ({ ...b, normal: total * w * Math.exp(-0.5 * ((b.x - mean) / std) ** 2) / (std * Math.sqrt(2 * Math.PI)) }))
  }, [d])

  const inPortfolio = holdings.some(h => h.ticker === ticker)
  return (
    <div>
      <PageHeader eyebrow="Research" title="Stock & Sector Explorer">
        Look up any stock or ETF: its history, how bumpy the ride was, how it moves with the market, and how it compares with its sector.
      </PageHeader>
      <div className="mb-5 grid gap-3 md:grid-cols-[1fr_auto]">
        <TickerSearch onPick={setTicker} />
        <Segmented value={period} onChange={setPeriod} options={['6m', '1y', '3y', '5y', '10y', 'max'].map(p => ({ value: p, label: p }))} />
      </div>
      {err && <Alert tone="loss">{err}</Alert>}
      {busy && !d && <Spinner label="Loading prices…" />}
      {d && (
        <div className="space-y-5">
          {d.synthetic && <Alert>Synthetic development data, not real prices.</Alert>}
          <Card title={<span className="flex items-baseline gap-2"><span className="num text-xl">{d.meta.ticker}</span><span className="font-normal text-muted">{d.meta.name}</span></span>}
            subtitle={`${d.meta.type} · ${d.meta.sector}${d.meta.industry ? ` · ${d.meta.industry}` : ''} · data: ${d.data.source}, ${d.stats.start} → ${d.stats.end} (updated ${d.data.last_updated?.slice(0, 10) ?? '—'})`}
            right={<Button variant={inPortfolio ? 'ghost' : 'primary'} disabled={inPortfolio} onClick={() => setHoldings([...holdings, { ticker, weight: 0 }])}><Plus size={14} />{inPortfolio ? 'In portfolio' : 'Add to portfolio'}</Button>}>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
              <Stat label="Last price" value={usd(d.stats.last_price, 2)} />
              <Stat label="Total return" value={pct(d.stats.total_return)} tone={d.stats.total_return >= 0 ? 'gain' : 'loss'} />
              <Stat label="Annualized" value={pct(d.stats.cagr)} tip="Compound annual growth rate over the selected period." />
              <Stat label="Volatility" value={pct(d.stats.volatility)} tip="Annualized standard deviation of daily returns: how bumpy the ride is." />
              <Stat label="Max drawdown" value={pct(d.stats.max_drawdown)} tone="loss" tip="Largest fall from a previous peak." />
              <Stat label="Sharpe" value={num(d.stats.sharpe)} tip="Return above a 3% risk-free rate per unit of volatility." />
              <Stat label="Corr. with SPY" value={num(d.stats.corr_with_spy)} tip="+1 moves exactly with the market; 0 unrelated." />
              <Stat label="Beta vs SPY" value={num(d.stats.beta_vs_spy)} tip="A 1% market move came with roughly this % move in the stock." />
            </div>
          </Card>
          <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
            <Card title="Price & trend" subtitle="Adjusted close with 50- and 200-day moving averages.">
              <div className="h-80">
                <ResponsiveContainer>
                  <ComposedChart data={d.series}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="date" minTickGap={60} /><YAxis width={56} domain={['auto', 'auto']} tickFormatter={v => `$${v.toFixed(0)}`} />
                    <Tooltip formatter={(v) => usd(Number(v), 2)} /><RLegend />
                    <Area dataKey="close" name="Price" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.08} strokeWidth={1.6} dot={false} isAnimationActive={false} />
                    <Line dataKey="sma50" name="50-day avg" stroke={CHART.series[3]} dot={false} strokeWidth={1.2} isAnimationActive={false} />
                    <Line dataKey="sma200" name="200-day avg" stroke={CHART.series[2]} dot={false} strokeWidth={1.2} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title="Daily return distribution" subtitle={`Bars: actual days. Line: a normal curve with the same mean and volatility. Kurtosis ${num(d.stats.kurtosis, 1)} (>0 means more extreme days than a normal curve predicts).`}>
              <div className="h-80">
                <ResponsiveContainer>
                  <ComposedChart data={normal}><XAxis dataKey="x" tickFormatter={v => pct(v, 0)} minTickGap={30} /><YAxis width={40} /><Tooltip formatter={(v) => (Number(v)).toFixed(1)} labelFormatter={l => pct(Number(l), 2)} />
                    <Bar dataKey="count" name="Days" fill="var(--accent)" isAnimationActive={false} /><Line dataKey="normal" name="Normal" stroke="var(--warn)" dot={false} strokeWidth={2} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Versus market & sector" subtitle="Each line starts at the same value, so you compare growth, not price levels.">
              <div className="h-64">
                <ResponsiveContainer>
                  <LineChart data={compare}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="date" minTickGap={60} /><YAxis width={56} domain={['auto', 'auto']} /><Tooltip formatter={(v) => usd(Number(v), 2)} /><RLegend />
                    <Line dataKey={d.meta.ticker} stroke="var(--accent)" dot={false} connectNulls isAnimationActive={false} strokeWidth={2} />
                    {Object.keys(d.comparisons).map((k, i) => <Line key={k} dataKey={k} name={`${k} (${d.comparisons[k].name})`} stroke={CHART.series[i + 3]} dot={false} connectNulls isAnimationActive={false} />)}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title="Drawdown" subtitle="How far below its previous high the price was on each day.">
              <div className="h-64">
                <ResponsiveContainer>
                  <AreaChart data={d.series}><XAxis dataKey="date" minTickGap={60} /><YAxis width={44} tickFormatter={v => pct(-Number(v), 0)} reversed /><Tooltip formatter={(v) => pct(-Number(v))} />
                    <Area dataKey="drawdown" stroke="var(--loss)" fill="var(--loss)" fillOpacity={0.2} isAnimationActive={false} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title="RSI (14-day)" subtitle="Momentum gauge. Above 70 is often called ‘overbought’, below 30 ‘oversold’. Descriptive only; not a trading signal.">
              <div className="h-48">
                <ResponsiveContainer>
                  <LineChart data={d.series}><XAxis dataKey="date" minTickGap={60} /><YAxis width={30} domain={[0, 100]} /><Tooltip /><ReferenceLine y={70} stroke="var(--loss)" strokeDasharray="3 3" /><ReferenceLine y={30} stroke="var(--gain)" strokeDasharray="3 3" />
                    <Line dataKey="rsi" stroke="var(--ai)" dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card title="MACD & rolling volatility" subtitle="MACD: gap between fast and slow trend averages. Rolling volatility shows calm vs. turbulent periods.">
              <div className="h-48">
                <ResponsiveContainer>
                  <ComposedChart data={d.series}><XAxis dataKey="date" minTickGap={60} /><YAxis yAxisId="m" width={40} /><YAxis yAxisId="v" orientation="right" width={40} tickFormatter={v => pct(v, 0)} /><Tooltip /><RLegend />
                    <Line yAxisId="m" dataKey="macd" name="MACD" stroke="var(--accent)" dot={false} isAnimationActive={false} />
                    <Line yAxisId="m" dataKey="signal" name="Signal" stroke={CHART.series[3]} dot={false} isAnimationActive={false} />
                    <Bar yAxisId="v" dataKey="vol63" name="63-day vol" fill="var(--warn)" fillOpacity={0.25} isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
          <SectorBoard />
        </div>
      )}
    </div>
  )
}

function SectorBoard() {
  const { uniMeta } = useStore()
  const [rows, setRows] = useState<any[] | null>(null)
  const [busy, setBusy] = useState(false)
  const load = async () => {
    setBusy(true)
    const entries = Object.entries(uniMeta.sector_etfs)
    const out = await Promise.all(entries.map(async ([sector, etf]) => {
      try { const d = await api.asset(etf, '1y'); return { sector, etf, ret: d.stats.total_return, vol: d.stats.volatility, dd: d.stats.max_drawdown } } catch { return { sector, etf, ret: null, vol: null, dd: null } }
    }))
    setRows(out.sort((a, b) => (b.ret ?? -9) - (a.ret ?? -9))); setBusy(false)
  }
  return (
    <Card title="Sector scoreboard (last 12 months)" subtitle="Each GICS sector represented by its Select Sector SPDR ETF." right={<Button variant="ghost" onClick={load} disabled={busy}>{busy ? <Spinner /> : null}Load sectors</Button>}>
      {rows && (
        <div className="h-72">
          <ResponsiveContainer>
            <BarChart data={rows} layout="vertical" margin={{ left: 40 }}><CartesianGrid stroke={CHART.grid} horizontal={false} /><XAxis type="number" tickFormatter={v => pct(v, 0)} /><YAxis type="category" dataKey="sector" width={150} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => pct(Number(v))} /><Bar dataKey="ret" name="1-year return" isAnimationActive={false}>{rows.map(r => <Cell key={r.etf} fill={(r.ret ?? 0) >= 0 ? 'var(--gain)' : 'var(--loss)'} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}
