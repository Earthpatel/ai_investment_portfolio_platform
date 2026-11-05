import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend as RLegend } from 'recharts'
import { BrainCircuit, CheckCircle2, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../lib/store'
import { num, pct } from '../lib/format'
import { Alert, Button, CHART, Card, PageHeader, Spinner, Stat } from '../components/ui'

const MODEL_ORDER = ['ridge', 'random_forest', 'hist_gbm', 'lightgbm', 'catboost', 'momentum_baseline', 'zero_baseline', 'shuffled_ridge']

export default function MLPage() {
  const { holdings, settings, setSettings } = useStore()
  const [status, setStatus] = useState<any>(null)
  const [res, setRes] = useState<any>(null)
  const [preds, setPreds] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)

  const refresh = () => api.mlResults().then(r => { setRes(r); return api.mlPredictions(holdings.map(h => h.ticker)).then(setPreds) }).catch(() => setRes(null))
  useEffect(() => { api.mlStatus().then(setStatus); refresh() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (status?.state !== 'running') return
    const id = setInterval(() => api.mlStatus().then(s => { setStatus(s); if (s.state !== 'running') { clearInterval(id); refresh() } }), 1200)
    return () => clearInterval(id)
  }, [status?.state]) // eslint-disable-line react-hooks/exhaustive-deps

  const train = async () => { setErr(null); try { setStatus(await api.mlTrain({ cost_bps: 10 })) } catch (e: any) { setErr(e.message) } }
  const models = res ? MODEL_ORDER.filter(k => res.models[k]) : []
  const best = res?.best_model
  const icData = res ? res.models[best].ic_series.map(([d, v]: [string, number]) => ({ date: d, ic: v, mom: Object.fromEntries(res.models.momentum_baseline.ic_series)[d] })) : []
  const cum = res ? (() => {
    const n = Math.max(...['ridge', best, 'momentum_baseline'].map(k => res.models[k]?.strategy?.cumulative.length ?? 0))
    return Array.from({ length: n }, (_, i) => ({ m: i + 1, ...Object.fromEntries(['ridge', best, 'momentum_baseline'].filter((v, j, a) => a.indexOf(v) === j).map(k => [k, res.models[k]?.strategy?.cumulative[i]])) }))
  })() : []
  const fi = res ? Object.entries<number>(res.feature_importance.random_forest).sort((a, b) => b[1] - a[1]).map(([f, v]) => ({ f, v })) : []

  return (
    <div>
      <PageHeader eyebrow="AI insights · experimental" title="AI & Machine Learning">
        Can patterns in past prices predict which stocks beat the average next month? This lab trains several models, tests them only on months they never saw, and compares them with simple baselines. If they don’t beat the baselines, it says so.
      </PageHeader>
      <Card tone="ai" title={<span className="flex items-center gap-2 text-ai"><BrainCircuit size={16} />Model training</span>}
        subtitle="Universe: your S&P 500 history. Target: next-21-trading-day return minus the average stock’s. Walk-forward validation with a 1-month embargo. Training runs in the background."
        right={<Button variant="ai" onClick={train} disabled={status?.state === 'running'}>{status?.state === 'running' ? <Spinner /> : null}{res ? 'Retrain' : 'Train models'}</Button>}>
        {status?.state === 'running' && (
          <div><div className="h-2 overflow-hidden rounded-full bg-panel-2"><div className="h-2 bg-ai transition-all" style={{ width: `${status.progress * 100}%` }} /></div>
            <div className="mt-1.5 text-[12px] text-muted">{status.message}</div></div>
        )}
        {status?.state === 'error' && <Alert tone="loss">{status.message}</Alert>}
        {err && <Alert tone="loss">{err}</Alert>}
        {!res && status?.state !== 'running' && <p className="text-[13px] text-faint">No trained models yet. Training takes about 1–3 minutes on the full S&P 500.</p>}
        {res && <div className="text-[12px] text-faint">Trained {res.trained_at.replace('T', ' ').slice(0, 16)} UTC · {res.universe_size} stocks · {res.months} months · {res.rows.toLocaleString()} samples · costs {res.cost_bps} bps{res.synthetic && <span className="text-warn"> · SYNTHETIC DEV DATA</span>}</div>}
      </Card>

      {res && (
        <div className="mt-5 space-y-5">
          <Alert tone={res.usable ? 'ai' : 'warn'}><b>{res.usable ? 'Signal detected (experimental).' : 'No reliable predictive skill.'}</b> {res.verdict}</Alert>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Best model" value={res.models[best].label.split(' (')[0]} tone="ai" />
            <Stat label="Out-of-sample IC" value={num(res.models[best].ic_mean, 3)} tip="Information coefficient: rank correlation between predictions and what actually happened, averaged across test months. 0 = no skill; 0.03–0.05 is already considered useful in practice." />
            <Stat label="IC t-statistic" value={num(res.models[best].ic_tstat, 1)} tone={(res.models[best].ic_tstat ?? 0) > 2 ? 'gain' : 'warn'} tip="Above ~2 suggests the IC is unlikely to be pure luck." />
            <Stat label="Leakage checks" value={res.leakage_checks_passed ? 'Passed' : 'FAILED'} tone={res.leakage_checks_passed ? 'gain' : 'loss'} tip="Every training label ends before its test period begins (embargo), and a model trained on shuffled labels should show ~0 IC." />
          </div>

          <Card title="Model comparison (out-of-sample only)" subtitle="Predictive accuracy (MAE, IC) and investment usefulness (top-20% strategy after costs) are different things: a model can be ‘accurate’ and still not make money after trading costs.">
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead className="text-left text-faint"><tr><th className="py-1.5">Model</th><th className="text-right">MAE</th><th className="text-right">RMSE</th><th className="text-right">Mean IC</th><th className="text-right">IC t-stat</th><th className="text-right">Hit rate</th><th className="text-right">Top-20% excess / yr (net)</th><th className="text-right">Excess Sharpe</th><th className="text-right">Turnover</th></tr></thead>
                <tbody>{models.map(k => { const m = res.models[k]; const isBase = k.includes('baseline') || k.includes('shuffled'); return (
                  <tr key={k} className={`border-t border-line ${k === best ? 'bg-ai/8' : ''}`}>
                    <td className={`py-2 ${isBase ? 'text-muted' : 'font-medium'}`}>{k === best && '★ '}{m.label}</td>
                    <td className="num text-right">{m.mae != null ? num(m.mae * 100, 3) + '%' : '—'}</td><td className="num text-right">{m.rmse != null ? num(m.rmse * 100, 3) + '%' : '—'}</td>
                    <td className={`num text-right ${(m.ic_mean ?? 0) > 0 ? 'text-gain' : 'text-loss'}`}>{num(m.ic_mean, 3)}</td><td className="num text-right">{num(m.ic_tstat, 1)}</td>
                    <td className="num text-right">{m.hit_rate != null ? pct(m.hit_rate) : '—'}</td>
                    <td className={`num text-right ${(m.strategy?.ann_excess_return ?? 0) > 0 ? 'text-gain' : 'text-loss'}`}>{m.strategy ? pct(m.strategy.ann_excess_return) : '—'}</td>
                    <td className="num text-right">{num(m.strategy?.ann_excess_sharpe)}</td><td className="num text-right">{m.strategy ? pct(m.strategy.avg_turnover, 0) : '—'}</td>
                  </tr>) })}</tbody>
              </table>
            </div>
            <p className="mt-2 text-[11px] text-faint">MAE/RMSE are on monthly relative returns: compare with “predict zero”. The shuffled-label row is a sanity check: its IC should be near zero.</p>
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Monthly IC over time" subtitle="Bars above zero: the model ranked stocks better than chance that month.">
              <div className="h-60"><ResponsiveContainer>
                <BarChart data={icData}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="date" minTickGap={40} /><YAxis width={40} /><Tooltip formatter={(v) => num(Number(v), 3)} /><ReferenceLine y={0} stroke="var(--faint)" />
                  <Bar dataKey="ic" name={res.models[best].label} fill="var(--ai)" isAnimationActive={false} />
                </BarChart></ResponsiveContainer></div>
            </Card>
            <Card title="Top-20% strategy vs average stock (after costs)" subtitle="Growth of $1 of excess return, out-of-sample months only.">
              <div className="h-60"><ResponsiveContainer>
                <LineChart data={cum}><CartesianGrid stroke={CHART.grid} vertical={false} /><XAxis dataKey="m" tickFormatter={v => `m${v}`} /><YAxis width={40} domain={['auto', 'auto']} /><Tooltip formatter={(v) => num(Number(v), 3)} /><RLegend /><ReferenceLine y={1} stroke="var(--faint)" />
                  {Object.keys(cum[0] ?? {}).filter(k => k !== 'm').map((k, i) => <Line key={k} dataKey={k} name={res.models[k].label} stroke={k === 'momentum_baseline' ? '#94a3b8' : CHART.series[i + 1]} dot={false} isAnimationActive={false} />)}
                </LineChart></ResponsiveContainer></div>
            </Card>
            <Card title="Feature importance (random forest)" subtitle="Which trailing signals the model leaned on. Importance is not causation.">
              <div className="h-64"><ResponsiveContainer>
                <BarChart data={fi} layout="vertical" margin={{ left: 20 }}><XAxis type="number" /><YAxis type="category" dataKey="f" width={100} interval={0} tick={{ fontSize: 11 }} /><Tooltip formatter={(v) => num(Number(v), 4)} /><Bar dataKey="v" fill="var(--ai)" isAnimationActive={false} /></BarChart>
              </ResponsiveContainer></div>
            </Card>
            <Card title="Walk-forward folds" subtitle="Train on the past, skip a month, test on the next six months, roll forward.">
              <div className="max-h-64 overflow-auto">
                <table className="w-full text-[11px]">
                  <thead className="sticky top-0 bg-panel text-left text-faint"><tr><th className="py-1">#</th><th>Train</th><th>Test</th><th className="text-right">Rows</th><th className="text-right">Embargo</th></tr></thead>
                  <tbody>{res.folds.map((f: any) => <tr key={f.fold} className="num border-t border-line"><td className="py-1">{f.fold}</td><td>{f.train_start} → {f.train_end}</td><td>{f.test_start} → {f.test_end}</td><td className="text-right">{f.train_rows.toLocaleString()} / {f.test_rows.toLocaleString()}</td>
                    <td className="text-right">{f.embargo_ok ? <CheckCircle2 size={13} className="inline text-gain" /> : <XCircle size={13} className="inline text-loss" />}</td></tr>)}</tbody>
                </table>
              </div>
            </Card>
          </div>

          <Card tone="ai" title="Your portfolio through the model’s eyes" subtitle={`Latest features as of ${res.latest_date}. Prediction = expected next-month return relative to the average stock. Not a recommendation.`}>
            {preds && (
              <div className="flex flex-wrap gap-2">
                {holdings.map(h => { const p = preds.predictions[h.ticker]; return (
                  <div key={h.ticker} className="rounded-xl border border-line bg-panel-2/60 px-3 py-2 text-[12px]">
                    <div className="num font-semibold">{h.ticker}</div>
                    {p ? <div className={p.pred_rel_21d >= 0 ? 'text-gain' : 'text-loss'}>{p.pred_rel_21d >= 0 ? '+' : ''}{(p.pred_rel_21d * 100).toFixed(2)}% vs avg · pct {Math.round(p.percentile * 100)}</div> : <div className="text-faint">not in training universe (ETFs excluded)</div>}
                  </div>) })}
              </div>
            )}
            <div className="mt-4 flex items-center gap-3">
              <label className={`inline-flex items-center gap-2 text-[13px] ${res.usable ? '' : 'opacity-50'}`}>
                <input type="checkbox" disabled={!res.usable} checked={settings.useMl && res.usable} onChange={e => setSettings({ useMl: e.target.checked })} />
                Use ML-tilted expected returns in the simulator (experimental)
              </label>
              {!res.usable && <span className="text-[12px] text-warn">Disabled: the model did not show reliable out-of-sample skill.</span>}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
