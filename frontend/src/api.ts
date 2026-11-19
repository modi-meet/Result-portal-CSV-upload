// Thin wrapper around the backend. Every failure becomes an ApiError with a message a person can read.

export type Problem = { line_no: number; student_id: string; field: string; code: string; message: string }
export type Group = { field: string; code: string; label: string; rows: number }

export type ImportReport = {
  id: number
  filename: string
  status: 'staged' | 'committed'
  created_at: string
  committed_at: string | null
  rows_read: number
  imported: number
  rejected: number
  removed: number
  new: number
  updated: number
  unchanged: number
  same_file_as: { id: number; committed_at: string } | null
  groups: Group[]
  problems_total: number
  problems: Problem[]
}

export type ImportSummary = Omit<ImportReport, 'same_file_as' | 'groups' | 'problems_total' | 'problems'>

export type FixLine = {
  line_no: number
  raw: string
  values: Record<string, string> | null
  edited: boolean
  removed: boolean
  problems: { field: string; code: string; message: string }[]
}
export type FixLines = { columns: string[]; lines: FixLine[] }

export type StudentRow = {
  student_id: string
  full_name: string
  grade_level: number
  section: string
  percentage: number
  grade: string
  passed: boolean
}
export type StudentPage = { items: StudentRow[]; total: number; page: number; page_size: number }

export type Student = StudentRow & {
  email: string
  date_of_birth: string
  total: number
  marks: { subject: string; mark: number; passed: boolean }[]
  rules: { pass_overall: number; pass_per_subject: number }
  source_file: string
  source_imported_at: string
  updated_at: string
}

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json()
    const d = body.detail
    if (d && typeof d === 'object' && 'message' in d) return new ApiError(res.status, d.code, d.message)
    if (Array.isArray(d)) return new ApiError(res.status, 'BAD_REQUEST', 'Some of the request values were not accepted.')
  } catch {
    /* not json */
  }
  if (res.status === 413) return new ApiError(413, 'TOO_LARGE', 'That file is too large to upload.')
  return new ApiError(res.status, 'SERVER', 'Something went wrong on the server. Please try again.')
}

const OFFLINE = () => new ApiError(0, 'NETWORK', "Can't reach the server. Check your connection and try again.")

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw OFFLINE()
  }
  if (!res.ok) throw await toError(res)
  return res.json()
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  report: (id: number, offset = 0, limit = 50) => request<ImportReport>(`/api/imports/${id}?offset=${offset}&limit=${limit}`),
  history: () => request<ImportSummary[]>('/api/imports'),
  lines: (id: number) => request<FixLines>(`/api/imports/${id}/lines`),
  editLine: (id: number, line: number, body: { values?: Record<string, string>; raw?: string; removed?: boolean }) =>
    request<FixLines & { report: ImportReport }>(`/api/imports/${id}/lines/${line}`, json('PATCH', body)),
  commit: (id: number) => request<ImportReport>(`/api/imports/${id}/commit`, { method: 'POST' }),
  students: (params: URLSearchParams, signal?: AbortSignal) => request<StudentPage>(`/api/students?${params}`, { signal }),
  student: (id: string, signal?: AbortSignal) => request<Student>(`/api/students/${encodeURIComponent(id)}`, { signal }),
  config: () => request<{ allow_clear: boolean; max_upload_mb: number }>('/api/config'),
  clearData: () => request<{ deleted: { students: number; imports: number } }>('/api/data', { method: 'DELETE' }),
  problemsCsvUrl: (id: number) => `/api/imports/${id}/problems.csv`,
  fixedCsvUrl: (id: number) => `/api/imports/${id}/file.csv`,

  /** XHR so we can show real upload progress. `onProgress` gets 0..1 while sending, then null while the server works. */
  upload(file: File, mode: 'import' | 'check', onProgress: (p: number | null) => void): Promise<ImportReport> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      const form = new FormData()
      form.append('file', file)
      xhr.open('POST', `/api/imports?mode=${mode}`)
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
      xhr.upload.onload = () => onProgress(null)
      xhr.onerror = () => reject(OFFLINE())
      xhr.onload = async () => {
        const res = new Response(xhr.responseText, { status: xhr.status, headers: { 'Content-Type': 'application/json' } })
        if (res.ok) resolve(await res.json())
        else reject(await toError(res))
      }
      xhr.send(form)
    })
  },
}
