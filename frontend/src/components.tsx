import { createContext, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { NavLink, Link } from 'react-router-dom'
import { useReveal } from './lib'
import { api } from './api'

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
          <Link to="/import" className="brand" aria-label="Results Portal home">
            <img src="/logo.svg" alt="" width="118" height="15" />
            <span className="brand-sub">Portal</span>
          </Link>
          <nav className="nav" aria-label="Main">
            <NavLink to="/import">Import</NavLink>
            <NavLink to="/students">Students</NavLink>
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

let configPromise: ReturnType<typeof api.config> | null = null
const useAllowClear = () => {
  const [allow, setAllow] = useState(false)
  useEffect(() => {
    configPromise ??= api.config().catch(() => ({ allow_clear: false, max_upload_mb: 10 }))
    configPromise.then((c) => setAllow(c.allow_clear))
  }, [])
  return allow
}

/** Wipes every student and import, behind a typed confirmation. */
export function ClearDataButton({ onCleared, disabled }: { onCleared: () => void; disabled?: boolean }) {
  const allow = useAllowClear()
  const dialog = useRef<HTMLDialogElement>(null)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!allow) return null

  const open = () => {
    setTyped('')
    setError(null)
    dialog.current?.showModal()
  }
  const clear = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.clearData()
      dialog.current?.close()
      onCleared()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button className="btn btn-danger btn-sm" onClick={open} disabled={disabled}>Clear all data</button>
      <dialog ref={dialog} className="modal" onClose={() => setTyped('')} aria-labelledby="clear-title">
        <form method="dialog" onSubmit={(e) => (e.preventDefault(), typed === 'delete' && clear())}>
          <span className="eyebrow" style={{ color: 'rgb(var(--bad))' }}>Can't be undone</span>
          <h2 id="clear-title">Clear all data?</h2>
          <p className="muted">Every student, report and import history will be deleted, and the portal will be empty again. Keep your CSV files if you want to import them later.</p>
          <label htmlFor="clear-confirm" className="field-label">Type <b>delete</b> to confirm</label>
          <input id="clear-confirm" className="input" style={{ width: '100%' }} value={typed} autoComplete="off" autoFocus
            onChange={(e) => setTyped(e.target.value.trim().toLowerCase())} />
          {error && <p className="row-msgs" role="alert" style={{ marginTop: 10 }}>{error}</p>}
          <div className="modal-actions">
            <button type="button" className="btn btn-ghost" onClick={() => dialog.current?.close()}>Cancel</button>
            <button type="submit" className="btn btn-danger-solid" disabled={typed !== 'delete' || busy}>{busy ? 'Clearing…' : 'Clear everything'}</button>
          </div>
        </form>
      </dialog>
    </>
  )
}
