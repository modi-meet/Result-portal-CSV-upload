import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams, useLocation } from 'react-router-dom'
import { api, ApiError, type StudentPage } from '../api'
import { Notice, Reveal, SearchIcon, useBusy } from '../components'
import { fmt, useDebounced } from '../lib'

const SIZES = [25, 50, 100]
type Sort = 'student_id' | 'full_name' | 'grade_level' | 'percentage'

export default function StudentsPage() {
  // everything lives in the URL, so refresh, back and shared links all work
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const q = params.get('q') ?? ''
  const grade = params.get('class') ?? ''
  const page = Math.max(1, Number(params.get('page')) || 1)
  const size = SIZES.includes(Number(params.get('size'))) ? Number(params.get('size')) : 25
  const sort = (params.get('sort') as Sort) || 'student_id'
  const order = params.get('order') === 'desc' ? 'desc' : 'asc'

  const [text, setText] = useState(q)
  const debounced = useDebounced(text.trim())
  const [data, setData] = useState<StudentPage | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  useBusy(loading)

  const update = (patch: Record<string, string | number | null>, resetPage = true) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) v === null || v === '' ? next.delete(k) : next.set(k, String(v))
    if (resetPage) next.delete('page')
    setParams(next, { replace: 'q' in patch })
  }

  useEffect(() => {
    setText(q)
  }, [q])
  useEffect(() => {
    if (debounced !== q) update({ q: debounced })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  useEffect(() => {
    const ctrl = new AbortController()
    const p = new URLSearchParams({ page: String(page), page_size: String(size), sort, order })
    if (q) p.set('q', q)
    if (grade) p.set('grade_level', grade)
    setLoading(true)
    setError(null)
    api.students(p, ctrl.signal)
      .then((d) => {
        setData(d)
        // asked for a page past the end (e.g. after a new search): jump to the last real page
        const last = Math.max(1, Math.ceil(d.total / size))
        if (page > last) update({ page: last }, false)
      })
      .catch((e) => e.name !== 'AbortError' && setError(e))
      .finally(() => !ctrl.signal.aborted && setLoading(false))
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, grade, page, size, sort, order, attempt])

  const pages = data ? Math.max(1, Math.ceil(data.total / size)) : 1
  const toggleSort = (col: Sort) =>
    update({ sort: col, order: sort === col && order === 'asc' ? 'desc' : col === 'percentage' && sort !== col ? 'desc' : 'asc' })
  const back = location.pathname + location.search
  const filtered = !!(q || grade)

  const SortTh = ({ col, label, className = '' }: { col: Sort; label: string; className?: string }) => (
    <th className={`sortable ${className}`} aria-sort={sort === col ? (order === 'asc' ? 'ascending' : 'descending') : undefined}>
      <button onClick={() => toggleSort(col)}>
        {label}
        <span aria-hidden style={{ opacity: sort === col ? 1 : 0.25 }}>{sort === col && order === 'desc' ? '↓' : '↑'}</span>
      </button>
    </th>
  )

  return (
    <>
      <Reveal className="page-head">
        <div>
          <span className="eyebrow">Students</span>
          <h1>Students</h1>
          <p className="muted">Search by name or student ID, filter by class, and open any student to see their report.</p>
        </div>
      </Reveal>

      <Reveal delay={80}>
        <div className="toolbar">
          <div className="search">
            <SearchIcon />
            <label className="sr-only" htmlFor="q">Search by name or student ID</label>
            <input id="q" className="input" placeholder="Search by name or student ID" value={text} onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === 'Escape' && setText('')} autoComplete="off" />
            {text && <button className="icon-btn clear" aria-label="Clear search" onClick={() => setText('')}>×</button>}
          </div>
          <label className="sr-only" htmlFor="class">Class</label>
          <select id="class" className="select" value={grade} onChange={(e) => update({ class: e.target.value })}>
            <option value="">All classes</option>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((g) => <option key={g} value={g}>Class {g}</option>)}
          </select>
        </div>

        <p className="meta-line muted" aria-live="polite">
          {data && !error && (data.total
            ? <>Showing {fmt((page - 1) * size + 1)} to {fmt(Math.min(page * size, data.total))} of {fmt(data.total)} students</>
            : null)}
        </p>

        {error ? (
          <div className="card empty">
            <h3>Couldn't load students</h3>
            <p className="muted">{error.message}</p>
            <button className="btn btn-primary" onClick={() => setAttempt(attempt + 1)}>Retry</button>
          </div>
        ) : data && data.total === 0 && !loading ? (
          <div className="card empty">
            {filtered ? (
              <>
                <h3>No students match {q ? `“${q}”` : 'this filter'}{grade && q ? ` in class ${grade}` : ''}</h3>
                <p className="muted">Check the spelling, or search by part of the name or ID.</p>
                <button className="btn btn-ghost" onClick={() => (setText(''), setParams(new URLSearchParams()))}>Clear search</button>
              </>
            ) : (
              <>
                <h3>No students yet</h3>
                <p className="muted">Import a CSV of term results and they'll show up here.</p>
                <Link className="btn btn-primary" to="/import">Import a file</Link>
              </>
            )}
          </div>
        ) : (
          <div className="table-wrap" style={{ opacity: loading && data ? 0.55 : 1, transition: 'opacity .2s' }}>
            <table>
              <thead>
                <tr>
                  <SortTh col="student_id" label="Student ID" />
                  <SortTh col="full_name" label="Name" />
                  <SortTh col="grade_level" label="Class" />
                  <th>Section</th>
                  <SortTh col="percentage" label="Percentage" className="right" />
                  <th>Grade</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {!data
                  ? Array.from({ length: 8 }, (_, i) => (
                      <tr key={i}>{[70, 160, 30, 20, 50, 20, 50].map((w, j) => <td key={j}><span className="skeleton" style={{ width: w }} /></td>)}</tr>
                    ))
                  : data.items.map((s) => (
                      <tr key={s.student_id} className="clickable" onClick={(e) => {
                        if ((e.target as HTMLElement).closest('a')) return
                        navigate(`/students/${encodeURIComponent(s.student_id)}`, { state: { back } })
                      }}>
                        <td className="num">{s.student_id}</td>
                        <td className="name"><Link to={`/students/${encodeURIComponent(s.student_id)}`} state={{ back }}>{s.full_name}</Link></td>
                        <td className="num">{s.grade_level}</td>
                        <td>{s.section}</td>
                        <td className="num right">{s.percentage.toFixed(1)}%</td>
                        <td>{s.grade}</td>
                        <td><span className={`pill ${s.passed ? 'pass' : 'fail'}`}>{s.passed ? 'Pass' : 'Fail'}</span></td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        )}

        {data && data.total > 0 && !error && (
          <div className="pager">
            <nav className="pages" aria-label="Pages">
              <button className="page-btn" disabled={page <= 1} onClick={() => update({ page: page - 1 }, false)} aria-label="Previous page">‹</button>
              {pageList(page, pages).map((p, i) =>
                p === 0 ? <span key={`gap${i}`} className="quiet">…</span> : (
                  <button key={p} className="page-btn" aria-current={p === page ? 'page' : undefined} onClick={() => update({ page: p }, false)}>{p}</button>
                ),
              )}
              <button className="page-btn" disabled={page >= pages} onClick={() => update({ page: page + 1 }, false)} aria-label="Next page">›</button>
            </nav>
            <label className="muted" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              Rows per page
              <select className="select" style={{ height: 34 }} value={size} onChange={(e) => update({ size: e.target.value })}>
                {SIZES.map((s) => <option key={s}>{s}</option>)}
              </select>
            </label>
          </div>
        )}
      </Reveal>
      {error && data && <Notice tone="error">{error.message}</Notice>}
    </>
  )
}

/** 1 … 4 5 [6] 7 8 … 188  (0 marks a gap) */
function pageList(current: number, total: number): number[] {
  const set = new Set([1, total, current - 1, current, current + 1].filter((p) => p >= 1 && p <= total))
  const sorted = [...set].sort((a, b) => a - b)
  const out: number[] = []
  sorted.forEach((p, i) => {
    if (i && p - sorted[i - 1] > 1) out.push(0)
    out.push(p)
  })
  return out
}
