import { useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { pct, usdShort, percentile } from '../lib/format'
import { Card, PageHeader, Segmented } from '../components/ui'

// Small seeded RNG so demos are reproducible
function rng(seed: number) {
  let s = seed >>> 0
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296 }
}
function normal(r: () => number) { const u = 1 - r(), v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) }

export default function Learn() {
  const [mode, setMode] = useState<'simple' | 'advanced'>('simple')
  return (
    <div>
      <PageHeader eyebrow="Education" title="Learn Monte Carlo">
        Monte Carlo means answering a question by running a random experiment many times and counting what happens. Start with a game show, then see how the same idea prices investment risk.
      </PageHeader>
      <div className="mb-5"><Segmented value={mode} onChange={setMode} options={[{ value: 'simple', label: 'Simple explanations' }, { value: 'advanced', label: 'Advanced (with the math)' }]} /></div>

      <Card title="Module 1 · The Monty Hall problem" subtitle="Three doors, one car. You pick a door, the host opens a goat door, and offers a switch. Play it, then let the computer play thousands of times."
        right={<a href="/monty-hall.html" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12px] text-accent">Open standalone page <ExternalLink size={12} /></a>}>
        <iframe src="/monty-hall.html" title="Monty Hall simulation" className="h-[900px] w-full rounded-xl border border-line bg-bg" />
        <p className="mt-3 text-[13px] text-muted">
          {mode === 'simple'
            ? 'Why switching wins about 2/3 of the time: your first pick is right only 1 time in 3. The host knows where the car is and always reveals a goat, so the leftover door carries the other 2/3.'
            : 'P(car behind your door) = 1/3 and does not change, because the host’s choice is constrained by knowledge (he never opens the car). The remaining closed door absorbs P = 2/3. Assumptions: the host always opens a goat door and always offers the switch. Change those rules and the answer changes.'}
        </p>
      </Card>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <RandomWalk mode={mode} />
        <Percentiles mode={mode} />
        <Correlation mode={mode} />
        <Concepts mode={mode} />
      </div>
    </div>
  )
}

function RandomWalk({ mode }: { mode: string }) {
  const [vol, setVol] = useState(18)
  const [ret, setRet] = useState(7)
  const [seed, setSeed] = useState(1)
  const data = useMemo(() => {
    const r = rng(seed), n = 12, years = 20
    const sm = vol / 100 / Math.sqrt(12), mu = Math.log(1 + ret / 100) / 12 - sm * sm / 2
    const paths = Array.from({ length: n }, () => { let v = 100; return Array.from({ length: years * 12 + 1 }, (_, m) => (m === 0 ? v : (v *= Math.exp(mu + sm * normal(r))))) })
    return Array.from({ length: years * 12 + 1 }, (_, m) => m % 3 === 0 ? { m: m / 12, ...Object.fromEntries(paths.map((p, i) => [`p${i}`, p[m]])) } : null).filter(Boolean)
  }, [vol, ret, seed])
  return (
    <Card title="Why simulated paths differ" subtitle={mode === 'simple' ? 'Same expected return, different luck. Turn up volatility and watch the paths fan out.' : 'Monthly log returns r ~ N(μ, σ²), with μ = ln(1+m)/12 − σ²/2 so the arithmetic mean is m. Value = 100·exp(Σr).'}
      right={<button onClick={() => setSeed(s => s + 1)} className="inline-flex items-center gap-1 text-[12px] text-accent"><RefreshCw size={12} />New luck</button>}>
      <div className="h-56"><ResponsiveContainer>
        <LineChart data={data as any[]}><CartesianGrid stroke="var(--grid)" vertical={false} /><XAxis dataKey="m" tickFormatter={v => `${v}y`} /><YAxis width={44} tickFormatter={v => `$${Math.round(v)}`} />
          {Array.from({ length: 12 }, (_, i) => <Line key={i} dataKey={`p${i}`} stroke="var(--accent)" strokeOpacity={0.5} dot={false} isAnimationActive={false} />)}
        </LineChart></ResponsiveContainer></div>
      <div className="mt-3 grid grid-cols-2 gap-4 text-[12px]">
        <label>Expected return: <b className="num">{ret}%</b><input type="range" min={0} max={15} value={ret} onChange={e => setRet(+e.target.value)} className="w-full" /></label>
        <label>Volatility: <b className="num">{vol}%</b><input type="range" min={0} max={50} value={vol} onChange={e => setVol(+e.target.value)} className="w-full" /></label>
      </div>
      <p className="mt-2 text-[12px] text-muted">{mode === 'simple' ? 'Volatility is how big the typical yearly swing is. A random variable is a number we can’t know in advance (next month’s return); the simulation draws it again and again.' : 'Volatility drag: the median path grows at ≈ m − σ²/2, so higher σ lowers typical outcomes even with the same arithmetic mean.'}</p>
    </Card>
  )
}

function Percentiles({ mode }: { mode: string }) {
  const [n, setN] = useState(1000)
  const data = useMemo(() => {
    const r = rng(7), sm = 0.18 / Math.sqrt(12), mu = Math.log(1.07) / 12 - sm * sm / 2
    const ends = Array.from({ length: n }, () => { let s = 0; for (let m = 0; m < 120; m++) s += mu + sm * normal(r); return 10000 * Math.exp(s) }).sort((a, b) => a - b)
    const bins = 30, lo = ends[Math.floor(n * 0.01)], hi = ends[Math.floor(n * 0.99)], w = (hi - lo) / bins
    const h = Array.from({ length: bins }, (_, i) => ({ x: lo + (i + 0.5) * w, c: 0 }))
    ends.forEach(e => { const k = Math.floor((e - lo) / w); if (k >= 0 && k < bins) h[k].c++ })
    return { h, p10: percentile(ends, 0.1), p50: percentile(ends, 0.5), p90: percentile(ends, 0.9), mean: ends.reduce((a, b) => a + b, 0) / n }
  }, [n])
  return (
    <Card title="Percentiles & probability distributions" subtitle={`$10,000 for 10 years at 7% expected return, 18% volatility · ${n.toLocaleString()} simulations`}>
      <div className="h-48"><ResponsiveContainer>
        <AreaChart data={data.h}><XAxis dataKey="x" tickFormatter={usdShort} minTickGap={30} /><YAxis width={30} /><Tooltip formatter={(v) => [v, 'sims']} labelFormatter={l => usdShort(Number(l))} />
          <Area dataKey="c" type="monotone" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.2} isAnimationActive={false} />
        </AreaChart></ResponsiveContainer></div>
      <div className="mt-2 grid grid-cols-4 gap-2 text-center text-[12px]">
        <div><div className="text-faint">10th</div><div className="num text-loss">{usdShort(data.p10)}</div></div>
        <div><div className="text-faint">Median</div><div className="num">{usdShort(data.p50)}</div></div>
        <div><div className="text-faint">Mean</div><div className="num">{usdShort(data.mean)}</div></div>
        <div><div className="text-faint">90th</div><div className="num text-gain">{usdShort(data.p90)}</div></div>
      </div>
      <div className="mt-3"><Segmented size="sm" value={n} onChange={setN} options={[100, 1000, 10000].map(v => ({ value: v, label: `${v.toLocaleString()} sims` }))} /></div>
      <p className="mt-2 text-[12px] text-muted">{mode === 'simple' ? 'The 10th percentile means 1 in 10 simulated futures ended lower. Notice the mean sits above the median: a few huge winners pull the average up, so the median is the more “typical” outcome.' : 'Terminal wealth is lognormal: right-skewed with mean exp(μT+σ²T/2) > median exp(μT). Sampling error of a percentile shrinks roughly as 1/√N; compare 100 vs 10,000 sims.'}</p>
    </Card>
  )
}

function Correlation({ mode }: { mode: string }) {
  const [rho, setRho] = useState(0.3)
  const s1 = 0.2, s2 = 0.2
  const vol = Math.sqrt(0.25 * s1 * s1 + 0.25 * s2 * s2 + 2 * 0.25 * rho * s1 * s2)
  return (
    <Card title="Why correlations matter" subtitle="Two assets, each 20% volatile, held 50/50.">
      <label className="text-[12px]">Correlation: <b className="num">{rho.toFixed(2)}</b><input type="range" min={-1} max={1} step={0.05} value={rho} onChange={e => setRho(+e.target.value)} className="w-full" /></label>
      <div className="mt-4 flex items-end gap-6">
        <div><div className="text-[12px] text-faint">Each asset</div><div className="num text-2xl">{pct(0.2, 0)}</div></div>
        <div><div className="text-[12px] text-faint">Portfolio volatility</div><div className="num text-4xl font-semibold text-accent">{pct(vol, 1)}</div></div>
      </div>
      <div className="mt-3 h-3 rounded-full bg-panel-2"><div className="h-3 rounded-full bg-accent transition-all" style={{ width: `${(vol / 0.2) * 100}%` }} /></div>
      <p className="mt-3 text-[12px] text-muted">{mode === 'simple' ? 'When assets move independently, their bad days partly cancel out: that is diversification. At correlation 1 there’s no benefit; at −1 risk can vanish entirely. In crises, correlations tend to jump up exactly when you need diversification most.' : 'σp² = w₁²σ₁² + w₂²σ₂² + 2w₁w₂ρσ₁σ₂. The simulator preserves ρ via a Cholesky factor of the (shrunk) covariance matrix, or by resampling whole historical months together.'}</p>
    </Card>
  )
}

function Concepts({ mode }: { mode: string }) {
  const items = mode === 'simple' ? [
    ['Expected return', 'The average outcome if you could live the same year many times. Not what you’ll get in any single year.'],
    ['Simulations ≠ guarantees', 'A simulation can only remix the assumptions you give it. If the future is stranger than the past, reality can land outside every band.'],
    ['Monte Carlo vs backtesting', 'A backtest replays the ONE path history actually took. Monte Carlo asks what MANY plausible paths could look like.'],
    ['Three methods here', 'Parametric: smooth bell-curve-style randomness. Bootstrap: shuffles real past months. Custom: your own guesses.'],
  ] : [
    ['Arithmetic vs geometric', 'Arithmetic mean E[R] vs compound rate exp(E[ln(1+R)])−1 ≈ E[R] − σ²/2. Projections compound log returns; inputs are reported both ways.'],
    ['Bootstrap', 'Circular block bootstrap of joint monthly return vectors (default 6-month blocks) keeps fat tails, cross-correlation and some autocorrelation, but cannot invent events absent from the sample.'],
    ['Estimation risk', 'Mean returns are estimated with large error (SE ≈ σ/√T). Ten years of 18% volatility gives ±5.7% on the annual mean, which is why optimizers are fragile.'],
    ['Metrics', 'Annualized return is time-weighted (independent of contributions). Probability of loss = #(terminal < contributions) / N simulations.'],
  ]
  return (
    <Card title={mode === 'simple' ? 'Key ideas' : 'Under the hood'}>
      <dl className="space-y-3">{items.map(([t, d]) => <div key={t}><dt className="text-[13px] font-semibold">{t}</dt><dd className="mt-0.5 text-[12px] leading-relaxed text-muted">{d}</dd></div>)}</dl>
    </Card>
  )
}
