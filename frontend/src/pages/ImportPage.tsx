import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, ApiError, type ImportReport, type ImportSummary } from '../api'
import { ClearDataButton, Notice, Reveal, Stat, useBusy } from '../components'
import { fmt, fmtBytes, fmtDate, LABELS, plural, REQUIRED_COLUMNS } from '../lib'
import FixImport from './FixImport'

const MAX_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB) || 10
const MAX_BYTES = MAX_MB * 1024 * 1024

export default function ImportPage() {
  const [params, setParams] = useSearchParams()
  const v2 = params.get('version') === '2'
  const id = Number(params.get('id')) || null

  const open = (newId: number | null) => {
    const next = new URLSearchParams()
    if (v2) next.set('version', '2')
    if (newId) next.set('id', String(newId))
    setParams(next)
    scrollTo({ top: 0 })
  }

  if (v2) return <FixImport id={id} onOpen={open} />

  return (
    <>
      <Reveal className="page-head">
        <div>
          <span className="eyebrow">Import</span>
          <h1>Import student results</h1>
          <p className="muted">
            Upload a CSV exported from your spreadsheet. Good rows go straight in. Anything we can't use is listed with the
            reason, so you know exactly what to fix.
          </p>
        </div>
      </Reveal>
      {id ? (
        <ReportView id={id} onAnother={() => open(null)} />
      ) : (
        <>
          <Uploader mode="import" actionLabel="Upload and import" onDone={(r) => open(r.id)} />
          <History />
        </>
      )}
    </>
  )
}

// ---------- upload ----------

export function Uploader({ mode, actionLabel, onDone }: {
  mode: 'import' | 'check'
  actionLabel: string
  onDone: (r: ImportReport) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [over, setOver] = useState(false)
  const [progress, setProgress] = useState<number | null | undefined>(undefined) // undefined = idle, null = server working
  const [error, setError] = useState<ApiError | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const busy = progress !== undefined
  useBusy(busy)

  const pick = (f: File | undefined) => {
    if (!f || busy) return
    setError(null)
    setFile(f)
    if (f.size > MAX_BYTES) setError(new ApiError(0, 'TOO_LARGE', `This file is ${fmtBytes(f.size)}. The limit is ${MAX_MB} MB, so split it into smaller files.`))
    else if (f.size === 0) setError(new ApiError(0, 'EMPTY_FILE', 'This file is empty.'))
  }

  const go = async () => {
    if (!file || busy) return
    setError(null)
    setProgress(0)
    try {
      onDone(await api.upload(file, mode, setProgress))
    } catch (e) {
      setError(e as ApiError)
    } finally {
      setProgress(undefined)
    }
  }

  const blocked = !!error && error.status === 0 && error.code !== 'NETWORK'

  return (
    <Reveal delay={80}>
      <div className="upload-grid">
        <div
          className={`card lift drop ${over ? 'over' : ''} ${busy ? 'disabled' : ''}`}
          role="button"
          tabIndex={0}
          aria-label="Choose a CSV file, or drop one here"
          onClick={() => !busy && input.current?.click()}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), input.current?.click())}
          onDragOver={(e) => (e.preventDefault(), setOver(true))}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => (e.preventDefault(), setOver(false), pick(e.dataTransfer.files[0]))}
        >
          <span className="drop-icon" aria-hidden>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 16V4M6 10l6-6 6 6M4 20h16" /></svg>
          </span>
          <h3>{over ? 'Drop it here' : 'Drag and drop a CSV file'}</h3>
          <p className="muted">or <span className="link-btn">choose a file</span> from your computer</p>
          <input ref={input} type="file" accept=".csv,text/csv" hidden onChange={(e) => (pick(e.target.files?.[0]), (e.target.value = ''))} />
        </div>

        <div className="card file-card">
          {file ? (
            <div>
              <span className="eyebrow">Selected file</span>
              <div className="file-name">{file.name}</div>
              <div className="quiet" style={{ marginTop: 4 }}>{fmtBytes(file.size)}</div>
            </div>
          ) : (
            <div>
              <span className="eyebrow">Before you upload</span>
              <p className="muted">Save the sheet as <b>CSV UTF-8</b>. The first row must have these column names, in any order:</p>
            </div>
          )}
          <div className="cols">
            {REQUIRED_COLUMNS.map((c) => <span key={c}>{c}</span>)}
          </div>

          {busy && (
            <div aria-live="polite">
              <div className={`bar ${progress === null ? 'busy' : ''}`}><i style={{ width: `${(progress ?? 0) * 100}%` }} /></div>
              <p className="quiet" style={{ marginTop: 8, fontSize: 12.5 }}>
                {progress === null ? 'Checking every row…' : `Uploading… ${Math.round((progress ?? 0) * 100)}%`}
              </p>
            </div>
          )}

          <div style={{ marginTop: 'auto', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button className="btn btn-primary" disabled={!file || busy || blocked} onClick={go}>
              {busy ? 'Working…' : actionLabel}
            </button>
            {file && !busy && <button className="btn btn-ghost" onClick={() => (setFile(null), setError(null))}>Clear</button>}
          </div>
        </div>
      </div>

      {error && (
        <div style={{ marginTop: 16 }}>
          <Notice
            tone="error"
            title={error.code === 'NETWORK' ? 'Upload failed' : "We couldn't import this file"}
            action={error.code === 'NETWORK' || error.code === 'SERVER' ? <button className="btn btn-ghost btn-sm" onClick={go}>Try again</button> : undefined}
          >
            {error.message}
            {error.code !== 'NETWORK' && error.code !== 'SERVER' && <p className="quiet" style={{ marginTop: 4 }}>Nothing was imported.</p>}
          </Notice>
        </div>
      )}
    </Reveal>
  )
}

// ---------- report ----------

export function ReportView({ id, initial, onAnother }: { id: number; initial?: ImportReport; onAnother: () => void }) {
  const [report, setReport] = useState<ImportReport | null>(initial ?? null)
  const [error, setError] = useState<ApiError | null>(null)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(!initial)
  useBusy(loading)

  const load = useCallback((off: number) => {
    setLoading(true)
    setError(null)
    api.report(id, off)
      .then((r) => (setReport(r), setOffset(off)))
      .catch((e) => setError(e))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    if (!initial) load(0)
  }, [load, initial])

  if (error && !report) {
    return error.status === 404
      ? <Notice tone="warn" title="Import not found" action={<button className="btn btn-ghost btn-sm" onClick={onAnother}>Start a new import</button>}>It may have expired or never existed.</Notice>
      : <Notice tone="error" title="Couldn't load this import" action={<button className="btn btn-ghost btn-sm" onClick={() => load(offset)}>Retry</button>}>{error.message}</Notice>
  }
  if (!report) return <div className="card card-pad"><span className="skeleton" style={{ width: '40%' }} /></div>

  const committed = report.status === 'committed'
  const pageSize = 50

  return (
    <>
      <Reveal className="section-head" as="section">
        <div>
          <span className="eyebrow">{committed ? 'Import finished' : 'Checked, not imported yet'}</span>
          <h2>{report.filename}</h2>
          <p className="quiet" style={{ marginTop: 6 }}>{fmtDate(report.committed_at ?? report.created_at, true)}</p>
        </div>
        <button className="btn btn-ghost" onClick={onAnother}>Import another file</button>
      </Reveal>

      <div className="stats">
        <Stat label="Rows read" value={fmt(report.rows_read)} note={report.removed ? `${fmt(report.removed)} removed by you` : 'blank lines are skipped'} />
        <Stat
          label="Imported" tone="good" delay={80} value={fmt(report.imported)}
          note={committed ? `${fmt(report.new)} new · ${fmt(report.updated)} updated · ${fmt(report.unchanged)} unchanged` : 'ready to import'}
        />
        <Stat label="Not imported" tone={report.rejected ? 'bad' : undefined} delay={160} value={fmt(report.rejected)}
          note={report.rejected ? plural(report.problems_total, 'problem') + ' found' : 'nothing to fix'} />
      </div>

      <div style={{ display: 'grid', gap: 10, marginTop: 16 }}>
        {report.same_file_as && (
          <Notice title="You've imported this exact file before">
            Last time was {fmtDate(report.same_file_as.committed_at, true)}. Students already in the portal were left as
            they were, which is why most rows show as unchanged.
          </Notice>
        )}
        {committed && report.imported === 0 && (
          <Notice tone="warn" title="No students were imported">Every row had a problem. Fix the rows below and upload the file again.</Notice>
        )}
        {committed && report.updated > 0 && (
          <Notice>{plural(report.updated, 'student')} already in the portal had different details, so their records now match this file.</Notice>
        )}
      </div>

      {report.rejected > 0 && (
        <>
          <section className="section">
            <Reveal className="section-head">
              <div>
                <span className="eyebrow">What went wrong</span>
                <h2>Reasons rows were left out</h2>
              </div>
              <a className="btn btn-ghost" href={api.problemsCsvUrl(report.id)} download>Download problem list (CSV)</a>
            </Reveal>
            <div className="reasons">
              {report.groups.map((g, i) => (
                <Reveal key={g.field + g.code} delay={Math.min(i, 6) * 50} className="reason">
                  <span>{g.label}</span>
                  <b>{fmt(g.rows)}</b>
                </Reveal>
              ))}
            </div>
          </section>

          <section className="section">
            <div className="section-head">
              <div>
                <span className="eyebrow">Row by row</span>
                <h2>Every problem</h2>
              </div>
              <span className="quiet">
                Showing {fmt(offset + 1)}–{fmt(Math.min(offset + pageSize, report.problems_total))} of {fmt(report.problems_total)}.
                Row numbers match the lines in your file.
              </span>
            </div>
            <div className="table-wrap" style={{ opacity: loading ? 0.55 : 1, transition: 'opacity .2s' }}>
              <table>
                <thead>
                  <tr><th style={{ width: 80 }}>Row</th><th style={{ width: 140 }}>Student ID</th><th style={{ width: 150 }}>Column</th><th>Problem</th></tr>
                </thead>
                <tbody>
                  {report.problems.map((p, i) => (
                    <tr key={`${p.line_no}-${p.field}-${i}`}>
                      <td className="num">{p.line_no}</td>
                      <td className="num">{p.student_id || <span className="quiet">(blank)</span>}</td>
                      <td>{LABELS[p.field] ?? p.field}</td>
                      <td>{p.message} <span className="code">{p.code}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {report.problems_total > pageSize && (
              <div className="pager">
                <button className="btn btn-ghost btn-sm" disabled={offset === 0 || loading} onClick={() => load(offset - pageSize)}>Previous</button>
                <span className="quiet">Page {offset / pageSize + 1} of {Math.ceil(report.problems_total / pageSize)}</span>
                <button className="btn btn-ghost btn-sm" disabled={offset + pageSize >= report.problems_total || loading} onClick={() => load(offset + pageSize)}>Next</button>
              </div>
            )}
          </section>
        </>
      )}

      {committed && report.imported > 0 && (
        <div style={{ marginTop: 40 }}>
          <Link className="btn btn-primary" to="/students">See students</Link>
        </div>
      )}
    </>
  )
}

function History() {
  const [items, setItems] = useState<ImportSummary[] | null>(null)
  const [params] = useSearchParams()
  useEffect(() => {
    api.history().then(setItems).catch(() => setItems([]))
  }, [])
  if (!items?.length) return null
  const v = params.get('version') === '2' ? 'version=2&' : ''
  return (
    <section className="section">
      <Reveal className="section-head">
        <div><span className="eyebrow">Earlier imports</span><h2>Recent files</h2></div>
        <ClearDataButton onCleared={() => setItems([])} />
      </Reveal>
      <div className="history">
        {items.map((it, i) => (
          <Reveal key={it.id} delay={Math.min(i, 6) * 50}>
            <Link to={`/import?${v}id=${it.id}`}>
              <span><b style={{ fontWeight: 500 }}>{it.filename}</b> <span className="quiet">· {fmtDate(it.committed_at ?? it.created_at, true)}</span></span>
              <span className="muted num">{fmt(it.imported)} imported · {fmt(it.rejected)} not imported</span>
            </Link>
          </Reveal>
        ))}
      </div>
    </section>
  )
}
