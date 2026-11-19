import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { Shell } from './components'
import ImportPage from './pages/ImportPage'
import StudentsPage from './pages/StudentsPage'
import StudentReport from './pages/StudentReport'
import './index.css'

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    scrollTo({ top: 0 })
  }, [pathname])
  return null
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ScrollToTop />
      <Shell>
        <Routes>
          <Route path="/" element={<Navigate to="/import" replace />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/students" element={<StudentsPage />} />
          <Route path="/students/:id" element={<StudentReport />} />
          <Route path="*" element={
            <div className="card empty"><h3>Page not found</h3><p className="muted">That link doesn't go anywhere.</p><Link className="btn btn-primary" to="/students">Go to students</Link></div>
          } />
        </Routes>
      </Shell>
    </BrowserRouter>
  </StrictMode>,
)
