import { create } from 'zustand'
import { delete_task, generateNote, get_task_status, getTasks } from '@/services/note.ts'
import { v4 as uuidv4 } from 'uuid'
import toast from 'react-hot-toast'

export type TaskStatus =
  | 'PENDING'
  | 'PARSING'
  | 'DOWNLOADING'
  | 'TRANSCRIBING'
  | 'SUMMARIZING'
  | 'FORMATTING'
  | 'SAVING'
  | 'SUCCESS'
  | 'FAILED'

export interface AudioMeta {
  cover_url: string
  duration: number
  file_path: string
  platform: string
  raw_info: {
    uploader?: string
    webpage_url?: string
    [key: string]: unknown
  } | null
  title: string
  video_id: string
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface Transcript {
  full_text: string
  language: string
  raw: unknown
  segments: Segment[]
}
export interface Markdown {
  ver_id: string
  content: string
  style: string
  model_name: string
  created_at: string
}

export interface TaskFormData {
  video_url: string
  link?: boolean
  screenshot?: boolean
  platform: string
  quality: string
  model_name: string
  provider_id: string
  format?: string[]
  style: string
  extras?: string
  video_understanding?: boolean
  video_interval?: number
  grid_size?: number[]
}

export interface Task {
  id: string
  markdown: string | Markdown[] //为了兼容之前的笔记
  transcript: Transcript
  status: TaskStatus
  source?: string
  platform: string
  audioMeta: AudioMeta
  createdAt: string
  updatedAt?: string
  formData: TaskFormData
}

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  addPendingTask: (taskId: string, platform: string, formData: Task['formData']) => void
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt'>>) => void
  loadTasks: () => Promise<void>
  syncTasks: () => Promise<void>
  removeTask: (id: string) => void
  clearTasks: () => void
  setCurrentTask: (taskId: string | null) => void
  getCurrentTask: () => Task | null
  retryTask: (id: string, payload?: Partial<TaskFormData>) => Promise<void>
}

export const useTaskStore = create<TaskStore>()((set, get) => ({
  tasks: [],
  currentTaskId: null,

  addPendingTask: (taskId: string, platform: string, formData: TaskFormData) =>
    set(state => ({
      tasks: [
        {
          formData: formData,
          id: taskId,
          status: 'PENDING',
          markdown: '',
          platform: platform,
          transcript: {
            full_text: '',
            language: '',
            raw: null,
            segments: [],
          },
          createdAt: new Date().toISOString(),
          audioMeta: {
            cover_url: '',
            duration: 0,
            file_path: '',
            platform: '',
            raw_info: null,
            title: '',
            video_id: '',
          },
        },
        ...state.tasks,
      ],
      currentTaskId: taskId, // 默认设置为当前任务
    })),

  updateTaskContent: (id, data) =>
    set(state => ({
      tasks: state.tasks.map(task => {
        if (task.id !== id) return task

        // 如果是 markdown 字符串，封装为版本
        if (typeof data.markdown === 'string') {
          const prev = task.markdown
          const newVersion: Markdown = {
            ver_id: `${task.id}-${uuidv4()}`,
            content: data.markdown,
            style: task.formData.style || '',
            model_name: task.formData.model_name || '',
            created_at: new Date().toISOString(),
          }

          let updatedMarkdown: Markdown[]
          if (Array.isArray(prev)) {
            updatedMarkdown = [newVersion, ...prev]
          } else {
            updatedMarkdown = [
              newVersion,
              ...(typeof prev === 'string' && prev
                ? [
                    {
                      ver_id: `${task.id}-${uuidv4()}`,
                      content: prev,
                      style: task.formData.style || '',
                      model_name: task.formData.model_name || '',
                      created_at: new Date().toISOString(),
                    },
                  ]
                : []),
            ]
          }

          return {
            ...task,
            ...data,
            markdown: updatedMarkdown,
          }
        }

        return { ...task, ...data }
      }),
    })),

  loadTasks: async () => {
    const tasks = await getTasks()
    set(state => ({
      tasks,
      currentTaskId:
        state.currentTaskId && tasks.some(task => task.id === state.currentTaskId)
          ? state.currentTaskId
          : null,
    }))
  },

  syncTasks: async () => {
    const summaries = await getTasks(false)
    const existingTasks = new Map(get().tasks.map(task => [task.id, task]))
    const tasksToHydrate: string[] = []

    const tasks = summaries.map(summary => {
      const existing = existingTasks.get(summary.id)
      if (!existing) {
        if (summary.status === 'SUCCESS') tasksToHydrate.push(summary.id)
        return summary
      }
      if (
        summary.status === 'SUCCESS' &&
        summary.updatedAt &&
        summary.updatedAt !== existing.updatedAt
      )
        tasksToHydrate.push(summary.id)
      return {
        ...existing,
        ...summary,
        markdown: existing.markdown,
        transcript: existing.transcript,
        audioMeta: existing.audioMeta,
      }
    })

    set(state => ({
      tasks,
      currentTaskId:
        state.currentTaskId && tasks.some(task => task.id === state.currentTaskId)
          ? state.currentTaskId
          : null,
    }))

    await Promise.all(
      tasksToHydrate.map(async id => {
        const result = await get_task_status(id)
        if (result.status !== 'SUCCESS' || !result.result) return
        const { markdown, transcript, audio_meta } = result.result
        get().updateTaskContent(id, {
          status: 'SUCCESS',
          markdown,
          transcript,
          audioMeta: audio_meta,
        })
      })
    )
  },

  getCurrentTask: () => {
    const currentTaskId = get().currentTaskId
    return get().tasks.find(task => task.id === currentTaskId) || null
  },
  retryTask: async (id: string, payload?: Partial<TaskFormData>) => {
    if (!id) {
      toast.error('任务不存在')
      return
    }
    const task = get().tasks.find(task => task.id === id)
    console.log('retry', task)
    if (!task) return

    const newFormData = { ...task.formData, ...payload }
    try {
      await generateNote({
        ...newFormData,
        task_id: id,
      })
    } catch (error: unknown) {
      const details =
        typeof error === 'object' && error !== null && 'data' in error
          ? (error as { data?: { reason?: string; downloading?: boolean } }).data
          : undefined
      // 就绪门禁：转写模型未下载好。不要把任务标成 PENDING（会一直转），
      // 给提示让用户先去下载。
      if (details?.reason === 'transcriber_model_not_ready') {
        toast.error(
          details.downloading
            ? '转写模型正在下载中，请稍候再重试'
            : '转写模型尚未下载，请先去「设置 → 音频转写配置」页下载'
        )
        return
      }
      console.error('重试任务失败：', error)
      return
    }

    set(state => ({
      tasks: state.tasks.map(t =>
        t.id === id
          ? {
              ...t,
              formData: newFormData, // ✅ 显式更新 formData
              status: 'PENDING',
            }
          : t
      ),
    }))
  },

  removeTask: async id => {
    const task = get().tasks.find(t => t.id === id)
    if (!task) return

    await delete_task(task.id)
    set(state => ({
      tasks: state.tasks.filter(task => task.id !== id),
      currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
    }))
  },

  clearTasks: () => set({ tasks: [], currentTaskId: null }),

  setCurrentTask: taskId => set({ currentTaskId: taskId }),
}))
