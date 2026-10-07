import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from './api/client'
import type { FixedBlock, Task } from './api/types'
import TasksPanel from './components/TasksPanel'
import FixedBlocksPanel from './components/FixedBlocksPanel'
import PlannerPanel from './components/PlannerPanel'
import './App.css'

function App() {
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
      if (!signal?.aborted) setTaskError(errorMessage(error))
    } finally { if (!signal?.aborted) setTaskLoading(false) }
  }, [])
  const refreshBlocks = useCallback(async (signal?: AbortSignal) => {
    setBlockLoading(true)
    setBlockError('')
    try { setBlocks(await api.blocks(signal)) }
    catch (error) {
      if (!signal?.aborted) setBlockError(errorMessage(error))
    } finally { if (!signal?.aborted) setBlockLoading(false) }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    void api.tasks(signal).then((items) => {
      if (!signal.aborted) setTasks(items)
    }).catch((error: unknown) => {
      if (!signal.aborted) setTaskError(errorMessage(error))
    }).finally(() => { if (!signal.aborted) setTaskLoading(false) })
    void api.blocks(signal).then((items) => {
      if (!signal.aborted) setBlocks(items)
    }).catch((error: unknown) => {
      if (!signal.aborted) setBlockError(errorMessage(error))
    }).finally(() => { if (!signal.aborted) setBlockLoading(false) })
    return () => controller.abort()
  }, [])

  const selectTask = (id: number | null) => {
    setSelectedTaskId(id)
    if (id !== null) document.getElementById('planner')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <main className="app">
      <header className="page-header">
        <div><span className="eyebrow">PERSONAL PLANNING</span><h1>LifeOps</h1></div>
        <p>Make room for your tasks. Review a recommendation, then book when you are ready.</p>
      </header>
      <div className="context-grid">
        <TasksPanel tasks={tasks} loading={taskLoading} error={taskError}
          onRefresh={() => refreshTasks()} onCreated={(task) => setTasks((current) => [...current, task])}
          onPlan={selectTask} />
        <FixedBlocksPanel blocks={blocks} loading={blockLoading} error={blockError}
          onRefresh={() => refreshBlocks()} onCreated={(block) => setBlocks((current) => [...current, block])} />
      </div>
      <PlannerPanel key={selectedTaskId ?? 'none'} tasks={tasks} selectedTaskId={selectedTaskId}
        onSelect={selectTask} onRefreshTasks={() => refreshTasks()} />
      <footer>Recommendations are suggestions. Booking rechecks current availability.</footer>
    </main>
  )
}
export default App
