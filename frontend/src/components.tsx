import { createContext, useContext, useEffect, useState, type CSSProperties, type ReactNode } from 'react'
import { NavLink, Link } from 'react-router-dom'
import { useReveal } from './lib'

/** Anything on the page can say "I'm busy" and the header's progress line shows it. */
const BusyContext = createContext<(busy: boolean) => void>(() => {})
export const useBusy = (busy: boolean) => {
  const set = useContext(BusyContext)
  useEffect(() => {
    set(busy)
    return () => set(false)
  }, [busy, set])
}

export function Shell({ children }: { children: ReactNode }) {
  const [stuck, setStuck] = useState(false)
  const [scroll, setScroll] = useState(0)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - innerHeight
      setStuck(scrollY > 4)
      setScroll(max > 0 ? scrollY / max : 0)
    }
    onScroll()
    addEventListener('scroll', onScroll, { passive: true })
    addEventListener('resize', onScroll)
    return () => {
      removeEventListener('scroll', onScroll)
      removeEventListener('resize', onScroll)
    }
  }, [])

  return (
    <BusyContext.Provider value={setBusy}>
      <header className={`header ${stuck ? 'is-stuck' : ''}`}>
        <div className="container">
          <Link to="/import" className="brand">
            <span className="brand-mark" aria-hidden>R</span>
            Results Portal
          </Link>
          <nav className="nav" aria-label="Main">
            <NavLink to="/import">Import</NavLink>
            <NavLink to="/students">Students</NavLink>
            <ThemeToggle />
          </nav>
        </div>
        {busy ? (
          <span className="progress-line busy" aria-hidden />
        ) : (
          <span className="progress-line" style={{ width: '100%', transform: `scaleX(${scroll})`, opacity: stuck ? 1 : 0 }} aria-hidden />
        )}
      </header>
      <main>
        <div className="container">{children}</div>
      </main>
    </BusyContext.Provider>
  )
}

function ThemeToggle() {
  const [dark, setDark] = useState(() =>
    document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches,
  )
  const flip = () => {
    const next = dark ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    try {
      localStorage.setItem('theme', next)
    } catch {
      /* private mode */
    }
    setDark(!dark)
  }
  return (
    <button className="icon-btn" onClick={flip} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}>
      {dark ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
      )}
    </button>
  )
}

/** Wraps children in the scroll reveal. `delay` staggers siblings (ms). */
export function Reveal({ children, delay = 0, className = '', as: Tag = 'div' }: {
  children: ReactNode; delay?: number; className?: string; as?: 'div' | 'section'
}) {
  const ref = useReveal<HTMLDivElement>()
  return (
    <Tag ref={ref} className={`rv ${className}`} style={{ transitionDelay: `${delay}ms` } as CSSProperties}>
      {children}
    </Tag>
  )
}

export function Notice({ tone = 'info', title, children, action }: {
  tone?: 'info' | 'warn' | 'error'; title?: string; children?: ReactNode; action?: ReactNode
}) {
  return (
    <div className={`notice ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span className="dot" aria-hidden />
      <div style={{ flex: 1 }}>
        {title && <strong>{title}</strong>}
        {children}
      </div>
      {action}
    </div>
  )
}

export function Stat({ label, value, note, tone, delay }: {
  label: string; value: string; note?: ReactNode; tone?: 'good' | 'bad'; delay?: number
}) {
  return (
    <Reveal delay={delay} className={`card lift stat ${tone ?? ''}`}>
      <span className="eyebrow">{label}</span>
      <div className="stat-value">{value}</div>
      {note && <div className="stat-note muted">{note}</div>}
    </Reveal>
  )
}

export const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
)
export const Arrow = ({ left }: { left?: boolean }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={left ? { transform: 'rotate(180deg)' } : undefined}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
)
