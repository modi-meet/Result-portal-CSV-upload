import { useEffect, useRef, useState } from 'react'

export const LABELS: Record<string, string> = {
  student_id: 'Student ID',
  full_name: 'Name',
  email: 'Email',
  date_of_birth: 'Date of birth',
  grade_level: 'Class',
  section: 'Section',
  maths: 'Maths',
  science: 'Science',
  english: 'English',
  social_studies: 'Social studies',
  second_language: 'Second language',
  row: 'Whole row',
}
export const REQUIRED_COLUMNS = Object.keys(LABELS).filter((k) => k !== 'row')

const nf = new Intl.NumberFormat('en-IN')
export const fmt = (n: number) => nf.format(n)
export const fmtMark = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0$/, ''))
export const plural = (n: number, one: string, many = one + 's') => `${fmt(n)} ${n === 1 ? one : many}`

export function fmtDate(iso: string, withTime = false) {
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso)
  return d.toLocaleString('en-IN', {
    day: 'numeric', month: 'long', year: 'numeric',
    ...(withTime ? { hour: 'numeric', minute: '2-digit' } : {}),
  })
}

export function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function useDebounced<T>(value: T, ms = 250) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

/** Fade-and-rise when an element scrolls into view. */
export function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          el.classList.add('in')
          io.disconnect()
        }
      },
      { rootMargin: '0px 0px -40px 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return ref
}
