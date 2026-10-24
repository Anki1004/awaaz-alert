import { useEffect, useRef } from 'react'

// Live waveform scope drawn from a rolling Float32 buffer (mic) — purely visual.
export function Scope({ wave, active, level }: { wave: Float32Array | null; active: boolean; level: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    let raf = 0
    const draw = () => {
      const c = ref.current
      if (!c) return
      const ctx = c.getContext('2d')!
      const W = (c.width = c.clientWidth * devicePixelRatio), H = (c.height = c.clientHeight * devicePixelRatio)
      ctx.clearRect(0, 0, W, H)
      ctx.lineWidth = 1.5 * devicePixelRatio
      ctx.strokeStyle = level === 'critical' ? '#ff5a5f' : level === 'high' ? '#ff9f43' : level === 'medium' ? '#f5b53f' : '#3ecf8e'
      ctx.beginPath()
      if (wave && active) {
        const step = Math.max(1, Math.floor(wave.length / W))
        for (let x = 0; x < W; x++) {
          let m = 0
          for (let j = 0; j < step; j++) m = Math.max(m, Math.abs(wave[x * step + j] || 0))
          const y = H / 2 - m * (H / 2) * 0.95
          const y2 = H / 2 + m * (H / 2) * 0.95
          ctx.moveTo(x, y); ctx.lineTo(x, y2)
        }
      } else {
        ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2)
      }
      ctx.stroke()
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [wave, active, level])
  return <canvas ref={ref} className="w-full h-[70px] block" />
}
