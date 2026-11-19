import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError, type FixLine, type ImportReport } from '../api'
import { Notice, Reveal, useBusy } from '../components'
import { fmt, LABELS, plural } from '../lib'
import { ReportView, Uploader } from './ImportPage'

type Tab = 'todo' | 'fixed' | 'removed' | 'all'
const PAGE = 40

/** v2: upload is only checked; the teacher fixes rows here, can download the fixed file, then imports once. */
export default function FixImport({ id, onOpen }: { id: number | null; onOpen: (id: number | null) => void }) {
  return (
    <>
      <Reveal className="page-head">
        <div>
          <span className="eyebrow">Import · check and fix</span>
          <h1>Fix problems before importing</h1>
          <p className="muted">
            We check the file first and nothing is saved yet. Fix or remove the rows with problems, download the corrected
            file for your records, then import.
          </p>
        </div>
      </Reveal>
      {id ? <Draft id={id} onAnother={() => onOpen(null)} /> : <Uploader mode="check" actionLabel="Upload and check" onDone={(r) => onOpen(r.id)} />}
    </>
  )
}

function Draft({ id, onAnother }: { id: number; onAnother: () => void }) {
  const [report, setReport] = useState<ImportReport | null>(null)
  const [lines, setLines] = useState<FixLine[] | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [tab, setTab] = useState<Tab>('todo')
  const [shown, setShown] = useState(PAGE)
  const [confirming, setConfirming] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [commitError, setCommitError] = useState<ApiError | null>(null)
  useBusy(committing || (!report && !error))

  const load = useCallback(() => {
    setError(null)
    api.report(id, 0, 1)
      .then(async (r) => {
        setReport(r)
        if (r.status === 'staged') setLines((await api.lines(id)).lines)
      })
      .catch(setError)
  }, [id])
  useEffect(load, [load])

  const counts = useMemo(() => {
    const c = { todo: 0, fixed: 0, removed: 0, all: lines?.length ?? 0 }
    for (const l of lines ?? []) {
      if (l.removed) c.removed++
      else if (l.problems.length) c.todo++
      else c.fixed++
    }
    return c
  }, [lines])

  const visible = useMemo(() => (lines ?? []).filter((l) =>
    tab === 'all' ? true : tab === 'removed' ? l.removed : tab === 'todo' ? !l.removed && l.problems.length > 0 : !l.removed && !l.problems.length,
  ), [lines, tab])

  const edit = async (line: number, body: Parameters<typeof api.editLine>[2]) => {
    const res = await api.editLine(id, line, body)
    setReport(res.report)
    setLines(res.lines)
  }

  const commit = async () => {
    setCommitting(true)
    setCommitError(null)
    try {
      setReport(await api.commit(id))
      scrollTo({ top: 0 })
    } catch (e) {
      setCommitError(e as ApiError)
    } finally {
      setCommitting(false)
      setConfirming(false)
    }
  }

  if (error) {
    return error.status === 404
      ? <Notice tone="warn" title="This check has expired" action={<button className="btn btn-ghost btn-sm" onClick={onAnother}>Upload again</button>}>Unfinished checks are kept for 24 hours.</Notice>
      : <Notice tone="error" title="Couldn't load this file" action={<button className="btn btn-ghost btn-sm" onClick={load}>Retry</button>}>{error.message}</Notice>
  }
  if (!report || (report.status === 'staged' && !lines)) {
    return <div className="card card-pad"><span className="skeleton" style={{ width: '50%' }} /><span className="skeleton" style={{ width: '30%', marginTop: 12 }} /></div>
  }
  if (report.status === 'committed') return <ReportView id={id} initial={report} onAnother={onAnother} />

  return (
    <>
      <div className="fix-bar">
        <div className="fix-counts" aria-live="polite">
          <span><b>{fmt(report.imported)}</b><span className="muted">ready</span></span>
          <span style={{ color: counts.todo ? 'rgb(var(--bad))' : undefined }}><b>{fmt(counts.todo)}</b>need fixing</span>
          <span><b>{fmt(counts.fixed)}</b><span className="muted">fixed</span></span>
          <span><b>{fmt(counts.removed)}</b><span className="muted">removed</span></span>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <a className="btn btn-ghost btn-sm" href={api.fixedCsvUrl(id)} download>Download fixed file</a>
          <button className="btn btn-primary btn-sm" disabled={!report.imported || committing}
            onClick={() => (counts.todo ? setConfirming(true) : commit())}>
            {committing ? 'Importing…' : `Import ${plural(report.imported, 'row')}`}
          </button>
        </div>
      </div>

      {confirming && (
        <div style={{ marginTop: 12 }}>
          <Notice tone="warn" title={`${plural(counts.todo, 'row')} still ${counts.todo === 1 ? 'has' : 'have'} problems`}
            action={<span style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirming(false)}>Keep fixing</button>
              <button className="btn btn-primary btn-sm" onClick={commit}>Import the rest</button>
            </span>}>
            They'll be left out, and the other {fmt(report.imported)} will be imported.
          </Notice>
        </div>
      )}
      {commitError && <div style={{ marginTop: 12 }}><Notice tone="error" title="Import failed">{commitError.message} Nothing was saved.</Notice></div>}

      <div className="toolbar" style={{ marginTop: 24, justifyContent: 'space-between' }}>
        <div className="tabs" role="group" aria-label="Which rows to show">
          {([['todo', 'Needs fixing'], ['fixed', 'Fixed'], ['removed', 'Removed'], ['all', 'All']] as const).map(([k, label]) => (
            <button key={k} aria-pressed={tab === k} onClick={() => (setTab(k), setShown(PAGE))}>{label} · {fmt(counts[k])}</button>
          ))}
        </div>
        <span className="quiet">{report.filename} · row numbers match your file</span>
      </div>

      {counts.all === 0 ? (
        <div className="card empty"><h3>Nothing to fix</h3><p className="muted">Every row passed the checks. Import whenever you're ready.</p></div>
      ) : visible.length === 0 ? (
        <div className="card empty">
          <h3>{tab === 'todo' ? 'All problems are sorted' : 'Nothing here'}</h3>
          <p className="muted">{tab === 'todo' ? 'Every row is now fixed or removed. You can import the file.' : 'Rows you change will show up here.'}</p>
        </div>
      ) : (
        <div className="fix-list">
          {visible.slice(0, shown).map((l) => <FixRow key={l.line_no} line={l} onEdit={edit} />)}
          {visible.length > shown && (
            <button className="btn btn-ghost" style={{ justifySelf: 'center' }} onClick={() => setShown(shown + PAGE)}>
              Show {Math.min(PAGE, visible.length - shown)} more of {fmt(visible.length - shown)}
            </button>
          )}
        </div>
      )}
    </>
  )
}

function FixRow({ line, onEdit }: { line: FixLine; onEdit: (line: number, body: Parameters<typeof api.editLine>[2]) => Promise<void> }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [raw, setRaw] = useState(line.raw)
  useEffect(() => {
    setRaw(line.raw)
  }, [line.raw])

  const byField = useMemo(() => {
    const m: Record<string, string[]> = {}
    for (const p of line.problems) (m[p.field] ??= []).push(p.message)
    return m
  }, [line.problems])

  const run = async (body: Parameters<typeof api.editLine>[2]) => {
    setSaving(true)
    setError(null)
    try {
      await onEdit(line.line_no, body)
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setSaving(false)
    }
  }

  const save = (field: string, value: string) => {
    if (line.values && value !== line.values[field]) run({ values: { [field]: value } })
  }

  const fixed = !line.removed && !line.problems.length
  const fields = line.values ? Object.keys(line.values).filter((f) => showAll || byField[f]) : []
  const id = line.values?.student_id?.trim() || line.raw.split(',')[0]?.trim()
  const name = line.values?.full_name?.trim()

  return (
    <div className={`card fix-row ${fixed ? 'fixed' : ''} ${line.removed ? 'removed' : ''}`}>
      <div className="fix-row-head">
        <div className="title">
          <h3 className="num">Row {line.line_no}</h3>
          <span className="muted">{[id || '(no ID)', name].filter(Boolean).join(' · ')}</span>
          {fixed && <span className="pill pass">Fixed</span>}
          {line.removed && <span className="pill neutral">Removed</span>}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {saving && <span className="saving quiet">Saving…</span>}
          {line.values && !line.removed && (
            <button className="link-btn" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show only problems' : 'Edit other columns'}</button>
          )}
          <button className={`btn btn-sm ${line.removed ? 'btn-ghost' : 'btn-danger'}`} disabled={saving} onClick={() => run({ removed: !line.removed })}>
            {line.removed ? 'Put back' : 'Remove row'}
          </button>
        </div>
      </div>

      {error && <p className="row-msgs" role="alert">{error}</p>}

      {!line.removed && (line.values ? (
        fields.length > 0 && (
          <div className="fix-fields">
            {fields.map((f) => (
              <div key={f + line.values![f]} className={`field ${byField[f] ? 'has-problem' : ''}`}>
                <label htmlFor={`l${line.line_no}-${f}`}>{LABELS[f]}</label>
                <input
                  id={`l${line.line_no}-${f}`}
                  defaultValue={line.values![f]}
                  placeholder="empty"
                  aria-invalid={!!byField[f]}
                  onBlur={(e) => save(f, e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && (e.currentTarget as HTMLInputElement).blur()}
                />
                {byField[f]?.map((m) => <div key={m} className="msg">{m}</div>)}
              </div>
            ))}
          </div>
        )
      ) : (
        <div>
          <ul className="row-msgs">{line.problems.map((p) => <li key={p.message}>{p.message}</li>)}</ul>
          <label className="sr-only" htmlFor={`raw-${line.line_no}`}>Row {line.line_no} as it appears in the file</label>
          <textarea id={`raw-${line.line_no}`} className="raw-edit" value={raw} onChange={(e) => setRaw(e.target.value)} spellCheck={false} />
          <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <button className="btn btn-ghost btn-sm" disabled={saving || raw === line.raw} onClick={() => run({ raw })}>Save line</button>
            <span className="quiet" style={{ fontSize: 12.5 }}>Values are separated by commas. Look for an extra or missing comma.</span>
          </div>
        </div>
      ))}
    </div>
  )
}
