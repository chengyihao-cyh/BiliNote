import { useEffect, useRef } from 'react'
import { useTaskStore } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import toast from 'react-hot-toast'

export const useTaskPolling = (interval = 3000, enabled = true) => {
  const tasks = useTaskStore(state => state.tasks)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const loadTasks = useTaskStore(state => state.loadTasks)
  const syncTasks = useTaskStore(state => state.syncTasks)

  const tasksRef = useRef(tasks)
  const pollCountRef = useRef(0)

  // 每次 tasks 更新，把最新的 tasks 同步进去
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  useEffect(() => {
    if (!enabled) return
    loadTasks().catch(error => console.error('加载任务历史失败：', error))
  }, [enabled, loadTasks])

  useEffect(() => {
    if (!enabled) return

    const timer = setInterval(async () => {
      pollCountRef.current += 1
      if (pollCountRef.current % 4 === 0) {
        try {
          await syncTasks()
        } catch (error) {
          console.error('同步任务历史失败：', error)
        }
      }

      const pendingTasks = tasksRef.current.filter(
        task => task.status != 'SUCCESS' && task.status != 'FAILED'
      )

      // 无活跃任务时跳过轮询
      if (pendingTasks.length === 0) return

      for (const task of pendingTasks) {
        try {
          const res = await get_task_status(task.id)
          const { status } = res

          if (status && status !== task.status) {
            if (status === 'SUCCESS' && res.result) {
              const { markdown, transcript, audio_meta } = res.result
              toast.success('笔记生成成功')
              updateTaskContent(task.id, {
                status,
                markdown,
                transcript,
                audioMeta: audio_meta,
              })
            } else if (status === 'FAILED') {
              updateTaskContent(task.id, { status })
              console.warn(`⚠️ 任务 ${task.id} 失败`)
            } else {
              updateTaskContent(task.id, { status })
            }
          }
        } catch (e) {
          console.error('❌ 任务轮询失败：', e)
        }
      }
    }, interval)

    return () => clearInterval(timer)
  }, [enabled, interval, syncTasks, updateTaskContent])
}
