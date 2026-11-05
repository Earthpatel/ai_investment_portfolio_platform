import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Activity, Briefcase, GraduationCap, ShieldAlert, Database } from 'lucide-react'
import { api } from '../lib/api'
import { PRESETS, useStore } from '../lib/store'
import { pct, usd } from '../lib/format'
import { AllocationDonut, Legend } from '../components/shared'
import { Card, Stat } from '../components/ui'

const STEPS = [
  ['Choose investments', '/builder'], ['Set amount & horizon', '/builder'], ['Review data & assumptions', '/builder'],
  ['Run the simulation', '/simulate'], ['Watch it unfold', '/simulate'], ['Explore risk', '/simulate'], ['Compare scenarios', '/risk'],
]

export default function Overview() {
  const { holdings, setHoldings, settings, result } = useStore()
  const [health, setHealth] = useState<any>(null)
  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)) }, [])
  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl border border-line bg-panel p-8 lg:p-10">
        <HeroPaths />
        <div className="relative max-w-2xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent">Monte Carlo Investment Lab</div>
          <h1 className="mt-3 font-display text-4xl font-semibold leading-tight tracking-tight lg:text-5xl">Thousands of possible futures for your money.</h1>
          <p className="mt-4 text-[15px] leading-relaxed text-muted">Pick real stocks and ETFs, set how much you invest and for how long, and watch a simulation build the range of outcomes from historical data. Then see the risks: losses, drawdowns, and how likely your goal is.</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/builder" className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-3 text-[14px] font-semibold text-white hover:brightness-110"><Briefcase size={16} />Build a portfolio</Link>
            <Link to="/simulate?run=1" className="inline-flex items-center gap-2 rounded-xl border border-line bg-panel-2 px-5 py-3 text-[14px] font-semibold hover:border-accent/60"><Activity size={16} />Simulate current portfolio</Link>
            <Link to="/learn" className="inline-flex items-center gap-2 rounded-xl px-4 py-3 text-[14px] text-muted hover:text-ink"><GraduationCap size={16} />How Monte Carlo works</Link>
          </div>
          <p className="mt-5 text-[12px] text-faint">Simulations show possibilities under stated assumptions, not predictions or advice.</p>
        </div>
      </section>

      <div className="grid gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {STEPS.map(([s, to], i) => (
          <Link key={s} to={to} className="group rounded-xl border border-line bg-panel p-3 hover:border-accent/50">
            <div className="num text-[11px] text-accent">STEP {i + 1}</div>
            <div className="mt-1 text-[13px] font-medium leading-snug">{s}</div>
          </Link>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Current portfolio" right={<Link to="/builder" className="text-[12px] text-accent">Edit →</Link>}>
          <AllocationDonut holdings={holdings} size={170} />
          <div className="mt-3"><Legend holdings={holdings} /></div>
          <div className="mt-3 text-[12px] text-muted">{usd(settings.initial)} initial{settings.contributionFreq !== 'none' && ` + ${usd(settings.contribution)} ${settings.contributionFreq}`} · {settings.years} years · {settings.method}</div>
        </Card>
        <Card title="Latest simulation" right={result && <Link to="/simulate" className="text-[12px] text-accent">Open →</Link>}>
          {result ? (
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Median ending value" value={usd(result.summary.median_end)} />
              <Stat label="Contributed" value={usd(result.summary.total_contributed)} />
              <Stat label="10th–90th pct" value={<span className="text-base">{usd(result.summary.p10_end)} – {usd(result.summary.p90_end)}</span>} />
              <Stat label="P(below contributions)" value={pct(result.summary.prob_below_contributions)} tone="loss" />
            </div>
          ) : <p className="text-[13px] text-faint">No simulation yet this session.</p>}
        </Card>
        <Card title={<span className="flex items-center gap-2"><Database size={15} />Data status</span>}>
          {health ? (
            <ul className="space-y-2 text-[13px]">
              <li className="flex justify-between"><span className="text-muted">API</span><span className="text-gain">Online</span></li>
              <li className="flex justify-between"><span className="text-muted">Price source</span><span className={health.dev_synthetic ? 'text-warn' : ''}>{health.dev_synthetic ? 'Synthetic (dev mode)' : 'yfinance + local cache'}</span></li>
              <li className="flex justify-between"><span className="text-muted">Live downloads</span><span>{health.network ? 'Enabled' : 'Off'}</span></li>
              <li className="flex justify-between"><span className="text-muted">Local S&P 500 history</span><span>{health.local_history ? 'Found' : 'Not found'}</span></li>
            </ul>
          ) : <p className="text-[13px] text-loss">API offline. Start the backend (see README).</p>}
        </Card>
      </div>

      <Card title="Start from an example" subtitle="Educational illustrations of common portfolio shapes, not recommendations.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {PRESETS.map(p => (
            <button key={p.name} onClick={() => setHoldings(p.holdings)} className="rounded-xl border border-line bg-panel-2/50 p-4 text-left hover:border-accent/60">
              <div className="text-[14px] font-semibold">{p.name}</div>
              <div className="mt-1 text-[12px] text-muted">{p.blurb}</div>
              <div className="num mt-2 text-[11px] text-faint">{p.holdings.map(h => `${h.ticker} ${h.weight}%`).join(' · ')}</div>
            </button>
          ))}
        </div>
      </Card>

      <div className="grid gap-5 md:grid-cols-2">
        <Link to="/risk"><Card title={<span className="flex items-center gap-2"><ShieldAlert size={15} className="text-warn" />Stress tests & what-ifs</span>}><p className="text-[13px] text-muted">Replay the 2008 crisis or the COVID crash on your weights, or add $100/month and see what changes. <ArrowRight size={13} className="inline" /></p></Card></Link>
        <Link to="/ml"><Card tone="ai" title={<span className="flex items-center gap-2 text-ai">AI & Machine Learning</span>}><p className="text-[13px] text-muted">Walk-forward tested models that report honestly when they don’t beat simple baselines. <ArrowRight size={13} className="inline" /></p></Card></Link>
      </div>
    </div>
  )
}

function HeroPaths() {
  // Purely decorative: deterministic pseudo-random walks (not data)
  const paths = Array.from({ length: 26 }, (_, k) => {
    let y = 300, s = (k + 1) * 9301
    const pts = [`M0 ${y}`]
    for (let x = 20; x <= 900; x += 20) {
      s = (s * 9301 + 49297) % 233280
      y += (s / 233280 - 0.56) * 26
      pts.push(`L${x} ${y.toFixed(1)}`)
    }
    return pts.join(' ')
  })
  return (
    <svg aria-hidden className="pointer-events-none absolute -right-20 top-0 h-full w-[900px] opacity-60 [mask-image:linear-gradient(to_left,black,transparent)]" viewBox="0 0 900 400" preserveAspectRatio="none">
      {paths.map((d, i) => <path key={i} d={d} fill="none" stroke="var(--accent)" strokeOpacity={0.12 + (i % 5) * 0.04} strokeWidth="1.2" />)}
    </svg>
  )
}
