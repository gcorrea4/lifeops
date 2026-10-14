import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errorMessage } from './api/client'
import type { FixedBlock, Task } from './api/types'
import TasksPanel from './components/TasksPanel'
import FixedBlocksPanel from './components/FixedBlocksPanel'
import PlannerPanel from './components/PlannerPanel'
import { useI18n } from './i18n/context'
import { useTheme } from './theme/context'
import { useActiveSection } from './useActiveSection'
import './App.css'

function App() {
  const { lang, setLang, t } = useI18n()
  const { theme, toggleTheme } = useTheme()
  const themeLabel = theme === 'dark' ? t.switchToLight : t.switchToDark
  const tRef = useRef(t)
  useEffect(() => { tRef.current = t }, [t])
  const [tasks, setTasks] = useState<Task[]>([])
  const [blocks, setBlocks] = useState<FixedBlock[]>([])
  const [taskLoading, setTaskLoading] = useState(true)
  const [blockLoading, setBlockLoading] = useState(true)
  const [taskError, setTaskError] = useState('')
  const [blockError, setBlockError] = useState('')
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null)

  const refreshTasks = useCallback(async (signal?: AbortSignal) => {
    setTaskLoading(true)
    setTaskError('')
    try { setTasks(await api.tasks(signal)) }
    catch (error) {
      if (!signal?.aborted) setTaskError(errorMessage(error, t))
    } finally { if (!signal?.aborted) setTaskLoading(false) }
  }, [t])
  const refreshBlocks = useCallback(async (signal?: AbortSignal) => {
    setBlockLoading(true)
    setBlockError('')
    try { setBlocks(await api.blocks(signal)) }
    catch (error) {
      if (!signal?.aborted) setBlockError(errorMessage(error, t))
    } finally { if (!signal?.aborted) setBlockLoading(false) }
  }, [t])

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    void api.tasks(signal).then((items) => {
      if (!signal.aborted) setTasks(items)
    }).catch((error: unknown) => {
      if (!signal.aborted) setTaskError(errorMessage(error, tRef.current))
    }).finally(() => { if (!signal.aborted) setTaskLoading(false) })
    void api.blocks(signal).then((items) => {
      if (!signal.aborted) setBlocks(items)
    }).catch((error: unknown) => {
      if (!signal.aborted) setBlockError(errorMessage(error, tRef.current))
    }).finally(() => { if (!signal.aborted) setBlockLoading(false) })
    return () => controller.abort()
  }, [])

  const selectTask = (id: number | null) => {
    setSelectedTaskId(id)
    if (id !== null) document.getElementById('planner')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const navItems = [
    { id: 'tasks', label: t.tasks },
    { id: 'commitments', label: t.commitments },
    { id: 'planner', label: t.planTask },
  ]
  const [activeSection, setActiveSection] = useActiveSection(navItems.map((item) => item.id))

  return (
    <div id="wrapper">
      {/* Hero background layer (gradient + scrim defined in index.css). */}
      <div className="bg" aria-hidden="true" />
      <header id="header">
        <a href="#top" className="logo">LifeOps</a>
      </header>
      <nav id="nav" aria-label={t.navLabel}>
        <ul className="links">
          {navItems.map((item) => <li key={item.id} className={activeSection === item.id ? 'active' : undefined}>
            <a href={'#' + item.id} aria-current={activeSection === item.id ? 'location' : undefined}
              onClick={() => setActiveSection(item.id)}>{item.label}</a>
          </li>)}
        </ul>
        <div className="controls">
          <div className="lang-switch" role="group" aria-label={t.language}>
            <button type="button" lang="en" aria-label="English" aria-pressed={lang === 'en'}
              onClick={() => setLang('en')}>EN</button>
            <button type="button" lang="pt-BR" aria-label="Português" aria-pressed={lang === 'pt'}
              onClick={() => setLang('pt')}>PT</button>
          </div>
          <button type="button" className="theme-toggle" onClick={toggleTheme}
            aria-label={themeLabel} title={themeLabel}>
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
              {theme === 'dark'
                ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>
                : <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />}
            </svg>
          </button>
        </div>
      </nav>
      <main id="main">
        <section id="top" className="post">
          <header className="major">
            <span className="date">{t.eyebrow}</span>
            <h1>{t.heroTitle}</h1>
            <p>{t.heroText}</p>
          </header>
          {/* Mascot: animated WebP with transparency; static frame for reduced motion. */}
          <picture className="hero-bob" aria-hidden="true">
            <source media="(prefers-reduced-motion: reduce)" srcSet="/images/bob-still.webp" />
            <img src="/images/bob.webp" alt="" width={290} height={334} decoding="async" />
          </picture>
        </section>
        <div className="context-grid">
          <TasksPanel tasks={tasks} loading={taskLoading} error={taskError}
            onRefresh={() => refreshTasks()} onCreated={(task) => setTasks((current) => [...current, task])}
            onPlan={selectTask} />
          <FixedBlocksPanel blocks={blocks} loading={blockLoading} error={blockError}
            onRefresh={() => refreshBlocks()} onCreated={(block) => setBlocks((current) => [...current, block])} />
        </div>
        <PlannerPanel key={selectedTaskId ?? 'none'} tasks={tasks} selectedTaskId={selectedTaskId}
          onSelect={selectTask} onRefreshTasks={() => refreshTasks()} />
      </main>
      <footer id="footer">
        <section>
          <h3>{t.aboutTitle}</h3>
          <p>{t.about}</p>
          <p>{t.footer}</p>
          <p>{t.sessionNote}</p>
        </section>
        <section className="split contact">
          {t.principles.map((item) => <section key={item.title}>
            <h3>{item.title}</h3>
            <p>{item.text}</p>
          </section>)}
        </section>
      </footer>
      <div id="copyright">
        <ul>
          <li>&copy; LifeOps</li>
          <li>{t.madeBy}</li>
        </ul>
      </div>
    </div>
  )
}
export default App
