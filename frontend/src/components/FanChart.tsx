/* Canvas fan chart. Draws `revealed` sample paths (the last one partially, so you watch it
 * travel through time), then the percentile band once the run is complete. */
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import type { SimResult } from '../lib/api'
import { usd, usdShort } from '../lib/format'

type Props = { result: SimResult; revealed: number; complete: boolean; real: boolean; goal?: number | null; height?: number }
export type FanChartHandle = { toPNG: () => string | null }

const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()

export const FanChart = forwardRef<FanChartHandle, Props>(function FanChart({ result, revealed, complete, real, goal, height = 420 }, ref) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const wrap = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(800)
  const [hover, setHover] = useState<{ x: number; m: number } | null>(null)
  useImperativeHandle(ref, () => ({ toPNG: () => canvas.current?.toDataURL('image/png') ?? null }))

  useEffect(() => {
    const ro = new ResizeObserver(e => setW(Math.max(300, e[0].contentRect.width)))
    if (wrap.current) ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [])

  const pad = { l: 64, r: 16, t: 14, b: 34 }
  const months = result.months.length - 1
  const infl = result.inflation_factor
  const adj = (v: number, m: number) => (real ? v / infl[m] : v)
  const P = real ? result.percentiles_real : result.percentiles
  // y-scale: cover the 95th percentile, not the single craziest path
  const yMax = Math.max(P['95'][months], ...result.contributions.map((c, m) => adj(c, m))) * 1.08
  const x = (m: number) => pad.l + (m / months) * (w - pad.l - pad.r)
  const y = (v: number) => pad.t + (1 - v / yMax) * (height - pad.t - pad.b)

  useEffect(() => {
    const c = canvas.current
    if (!c) return
    const dpr = window.devicePixelRatio || 1
    c.width = w * dpr; c.height = height * dpr
    const g = c.getContext('2d')!
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    g.clearRect(0, 0, w, height)
    g.fillStyle = css('--panel'); g.fillRect(0, 0, w, height)

    // grid + axes
    g.font = '11px Inter, sans-serif'; g.fillStyle = css('--muted'); g.strokeStyle = css('--grid'); g.lineWidth = 1
    for (let i = 0; i <= 5; i++) {
      const v = (yMax / 5) * i
      g.beginPath(); g.moveTo(pad.l, y(v)); g.lineTo(w - pad.r, y(v)); g.stroke()
      g.textAlign = 'right'; g.fillText(usdShort(v), pad.l - 8, y(v) + 4)
    }
    const yrs = months / 12
    const stepY = yrs <= 5 ? 1 : yrs <= 15 ? 2 : yrs <= 30 ? 5 : 10
    g.textAlign = 'center'
    for (let yr = 0; yr <= yrs; yr += stepY) g.fillText(`${yr}y`, x(yr * 12), height - 12)

    // sample paths
    const n = result.sample_paths.length
    const full = Math.max(0, Math.min(n, Math.floor(revealed)))
    const frac = revealed - full
    const pathColor = css('--path')
    g.lineWidth = 1
    const drawPath = (p: number[], upto: number, color: string) => {
      if (!p) return
      g.strokeStyle = color; g.beginPath()
      for (let m = 0; m <= upto; m++) { const px = x(m), py = y(Math.min(adj(p[m], m), yMax * 1.5)); m ? g.lineTo(px, py) : g.moveTo(px, py) }
      g.stroke()
    }
    for (let i = 0; i < full; i++) drawPath(result.sample_paths[i], months, pathColor)
    if (full < n && frac > 0) { g.lineWidth = 2; drawPath(result.sample_paths[full], Math.floor(frac * months), css('--accent')); g.lineWidth = 1 }

    // percentile bands (revealed when the run completes)
    if (complete) {
      const band = (lo: string, hi: string, color: string) => {
        g.fillStyle = color; g.beginPath()
        for (let m = 0; m <= months; m++) g.lineTo(x(m), y(P[hi][m]))
        for (let m = months; m >= 0; m--) g.lineTo(x(m), y(P[lo][m]))
        g.closePath(); g.fill()
      }
      band('10', '90', css('--band-2'))
      band('25', '75', css('--band'))
      const line = (k: string, color: string, width = 1.5, dash: number[] = []) => {
        g.strokeStyle = color; g.lineWidth = width; g.setLineDash(dash); g.beginPath()
        for (let m = 0; m <= months; m++) m ? g.lineTo(x(m), y(P[k][m])) : g.moveTo(x(m), y(P[k][m]))
        g.stroke(); g.setLineDash([])
      }
      line('90', css('--gain'), 1.2, [4, 4]); line('10', css('--loss'), 1.2, [4, 4]); line('50', css('--text'), 2.2)
    }
    // contributions
    g.strokeStyle = css('--warn'); g.lineWidth = 1.8; g.setLineDash([6, 4]); g.beginPath()
    result.contributions.forEach((c, m) => (m ? g.lineTo(x(m), y(adj(c, m))) : g.moveTo(x(m), y(adj(c, m)))))
    g.stroke(); g.setLineDash([])
    if (goal && goal < yMax) {
      g.strokeStyle = css('--ai'); g.lineWidth = 1; g.setLineDash([2, 3]); g.beginPath(); g.moveTo(pad.l, y(goal)); g.lineTo(w - pad.r, y(goal)); g.stroke(); g.setLineDash([])
      g.fillStyle = css('--ai'); g.textAlign = 'left'; g.fillText(`Goal ${usdShort(goal)}`, pad.l + 6, y(goal) - 5)
    }
    if (hover) { g.strokeStyle = css('--faint'); g.lineWidth = 1; g.beginPath(); g.moveTo(x(hover.m), pad.t); g.lineTo(x(hover.m), height - pad.b); g.stroke() }
  }, [result, revealed, complete, real, goal, w, height, hover])

  const onMove = (e: React.MouseEvent) => {
    const r = canvas.current!.getBoundingClientRect()
    const px = e.clientX - r.left
    const m = Math.round(((px - pad.l) / (w - pad.l - pad.r)) * months)
    if (m < 0 || m > months) return setHover(null)
    setHover({ x: px, m })
  }

  return (
    <div ref={wrap} className="relative w-full">
      <canvas ref={canvas} style={{ width: w, height }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}
        role="img" aria-label="Fan chart of simulated portfolio values over time" className="rounded-xl" />
      {hover && (
        <div className="pointer-events-none absolute top-3 z-10 w-52 rounded-lg border border-line bg-panel/95 p-2.5 text-[12px] shadow-xl"
          style={{ left: Math.min(hover.x + 14, w - 220) }}>
          <div className="mb-1 font-semibold">Year {(hover.m / 12).toFixed(hover.m % 12 ? 1 : 0)}{real ? ' · today’s $' : ''}</div>
          {[['90', '90th pct', 'text-gain'], ['75', '75th pct', ''], ['50', 'Median', 'font-semibold'], ['25', '25th pct', ''], ['10', '10th pct', 'text-loss']].map(([k, l, c]) => (
            <div key={k} className="flex justify-between"><span className="text-muted">{l}</span><span className={`num ${c}`}>{usd(P[k][hover.m])}</span></div>
          ))}
          <div className="mt-1 flex justify-between border-t border-line pt-1"><span className="text-warn">Contributed</span><span className="num">{usd(adj(result.contributions[hover.m], hover.m))}</span></div>
        </div>
      )}
    </div>
  )
})
