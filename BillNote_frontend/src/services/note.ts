import request from '@/utils/request'
import toast from 'react-hot-toast'
import type { AudioMeta, Task, TaskStatus, Transcript } from '@/store/taskStore'

interface GeneratedTask {
  task_id: string
}

interface TaskStatusResponse {
  status: TaskStatus
  result?: {
    markdown: string
    transcript: Transcript
    audio_meta: AudioMeta
  }
}

export const generateNote = async (
  data: Task['formData'] & {
    task_id?: string
  }
) => {
  try {
    console.log('generateNote', data)
    const response = (await request.post('/generate_note', data)) as unknown as GeneratedTask
    toast.success('笔记生成任务已提交！')

    console.log('res', response)
    // 成功提示

    return response
  } catch (e: unknown) {
    console.error('❌ 请求出错', e)

    // 错误提示
    // toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}

export const getTasks = async (includeResults = true): Promise<Task[]> => {
  return (await request.get('/tasks', {
    params: { include_results: includeResults },
  })) as unknown as Task[]
}

export const delete_task = async (taskId: string) => {
  try {
    const res = await request.post('/delete_task', { task_id: taskId })

    toast.success('任务已成功删除')
    return res
  } catch (e) {
    toast.error('请求异常，删除任务失败')
    console.error('❌ 删除任务失败:', e)
    throw e
  }
}

export const get_task_status = async (task_id: string): Promise<TaskStatusResponse> => {
  try {
    // 成功提示

    return (await request.get('/task_status/' + task_id)) as unknown as TaskStatusResponse
  } catch (e) {
    console.error('❌ 请求出错', e)

    // 错误提示
    toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}
