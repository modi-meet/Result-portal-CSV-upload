import { useEffect, useState } from 'react'
import { Link, useLocation, useParams, Navigate } from 'react-router-dom'
import { api, ApiError, type Student } from '../api'
import { Arrow, Reveal, useBusy } from '../components'
import { fmtDate, fmtMark, LABELS } from '../lib'

export default function StudentReport() {
  const { id = '' } = useParams()
  const location = useLocation()
  const back: string = location.state?.back ?? '/students'
  const [student, setStudent] = useState<Student | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)
  useBusy(!student && !error)

  useEffect(() => {
    const ctrl = new AbortController()
    setStudent(null)
    setError(null)
    api.student(id, ctrl.signal).then(setStudent).catch((e) => e.name !== 'AbortError' && setError(e))
    return () => ctrl.abort()
  }, [id, attempt])

  useEffect(() => {
    document.title = student ? `${student.full_name} · Results Portal` : 'Results Portal'
    return () => void (document.title = 'Results Portal')
  }, [student])

  // /students/stu00001 -> /students/STU00001
  if (student && student.student_id !== id) return <Navigate to={`/students/${student.student_id}`} replace state={location.state} />

  const backLink = <Link className="back" to={back}><Arrow left /> Back to students</Link>

  if (error) {
    return (
      <>
        {backLink}
        <div className="card empty">
          {error.status === 404 ? (
            <>
              <h3>Student not found</h3>
              <p className="muted">There's no student with ID “{id.toUpperCase()}”. They may not have been imported, or the ID has a typo.</p>
              <Link className="btn btn-primary" to="/students">Go to all students</Link>
            </>
          ) : (
            <>
              <h3>Couldn't load this report</h3>
              <p className="muted">{error.message}</p>
              <button className="btn btn-primary" onClick={() => setAttempt(attempt + 1)}>Retry</button>
            </>
          )}
        </div>
      </>
    )
  }

  if (!student) {
    return (
      <>
        {backLink}
        <div className="report-top">
          <div className="card profile"><span className="avatar" /><div style={{ flex: 1 }}><span className="skeleton" style={{ width: '60%', height: 22 }} /><span className="skeleton" style={{ width: '40%', marginTop: 14 }} /></div></div>
          <div className="card overall"><span className="skeleton" style={{ width: '50%', height: 40 }} /></div>
        </div>
      </>
    )
  }

  const initials = student.full_name.split(/[\s,]+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase()
  const failed = student.marks.filter((m) => !m.passed)
  const lowOverall = student.percentage < student.rules.pass_overall

  return (
    <>
      {backLink}
      <div className="report-top">
        <Reveal className="card profile">
          <span className="avatar" aria-hidden>{initials}</span>
          <div>
            <h1>{student.full_name}</h1>
            <dl>
              <dt>Student ID</dt><dd className="num">{student.student_id}</dd>
              <dt>Class</dt><dd>Class {student.grade_level}, Section {student.section}</dd>
              <dt>Email</dt><dd>{student.email}</dd>
              <dt>Date of birth</dt><dd>Born {fmtDate(student.date_of_birth)}</dd>
            </dl>
          </div>
        </Reveal>
        <Reveal delay={80} className="card lift overall">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
            <span className="eyebrow" style={{ margin: 0 }}>Overall</span>
            <span className={`pill ${student.passed ? 'pass' : 'fail'}`}>{student.passed ? 'Pass' : 'Fail'}</span>
          </div>
          <div className="overall-main">
            <span className="big-pct">{student.percentage.toFixed(1)}%</span>
            <span><span className="quiet" style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>Grade</span><span className="big-grade">{student.grade}</span></span>
          </div>
          <div style={{ fontWeight: 600 }} className="num">Total: {fmtMark(student.total)} / 500</div>
          {!student.passed && (
            <p className="muted" style={{ fontSize: 13 }}>
              {lowOverall ? `Below the ${student.rules.pass_overall}% needed overall` : ''}
              {lowOverall && failed.length ? '; ' : ''}
              {failed.length ? `below ${student.rules.pass_per_subject} in ${failed.map((m) => LABELS[m.subject].toLowerCase()).join(', ')}` : ''}.
            </p>
          )}
        </Reveal>
      </div>

      <section className="section">
        <Reveal className="section-head">
          <div><span className="eyebrow">Marks</span><h2>Marks by subject</h2></div>
          <button className="btn btn-ghost no-print" onClick={() => print()}>Print report</button>
        </Reveal>
        <Reveal delay={80} className="table-wrap">
          <table className="marks">
            <thead><tr><th>Subject</th><th className="right" style={{ width: 120 }}>Marks (out of 100)</th><th style={{ width: '45%' }}><span className="sr-only">Bar</span></th></tr></thead>
            <tbody>
              {student.marks.map((m, i) => (
                <tr key={m.subject}>
                  <td>{LABELS[m.subject]} {!m.passed && <span className="pill fail" style={{ marginLeft: 8, height: 22 }}>Below {student.rules.pass_per_subject}</span>}</td>
                  <td className="num right" style={{ fontWeight: 600 }}>{fmtMark(m.mark)}</td>
                  <td><div className="mark-bar"><i className={m.passed ? '' : 'low'} style={{ width: `${m.mark}%`, animationDelay: `${i * 80}ms` }} /></div></td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr><td>Total</td><td className="num right">{fmtMark(student.total)} / 500</td><td /></tr></tfoot>
          </table>
        </Reveal>
        <p className="scheme quiet">
          Grades: A 80% and above, B 60–79, C 50–59, D 40–49, F below 40. A pass needs at least {student.rules.pass_overall}% overall
          and at least {student.rules.pass_per_subject} in every subject. Last updated from {student.source_file} on {fmtDate(student.updated_at, true)}.
        </p>
      </section>
    </>
  )
}
