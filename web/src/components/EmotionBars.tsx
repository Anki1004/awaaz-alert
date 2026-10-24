const ORDER = ['fearful', 'sad', 'angry', 'surprised', 'neutral', 'happy', 'disgusted', 'other'] as const
const COLOR: Record<string, string> = {
  fearful: 'var(--color-red)', sad: 'var(--color-blue)', angry: '#ff9f43', surprised: 'var(--color-violet)',
  neutral: '#6b7d93', happy: 'var(--color-green)', disgusted: '#c0795a', other: '#3a4654',
}

export function EmotionBars({ probs }: { probs: Record<string, number> | null }) {
  return (
    <div className="p-3 space-y-[7px]">
      {ORDER.map((k) => {
        const v = probs?.[k] ?? 0
        return (
          <div key={k} className="flex items-center gap-2 text-[12px]">
            <span className="w-16 text-[var(--color-ink-dim)] capitalize">{k}</span>
            <div className="flex-1 h-[6px] rounded bg-[#17212b] overflow-hidden">
              <div className="h-full rounded" style={{ width: `${Math.round(v * 100)}%`, background: COLOR[k], transition: 'width .4s' }} />
            </div>
            <span className="mono w-8 text-right text-[var(--color-ink-dim)]">{Math.round(v * 100)}</span>
          </div>
        )
      })}
    </div>
  )
}
