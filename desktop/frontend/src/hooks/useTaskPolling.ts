import { useEffect, useRef } from 'react'
import { useTaskStore, type ConversationMessage, type Task, type TaskStatus } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import toast from 'react-hot-toast'
import { shouldShowTaskStatusToast } from '@/pages/HomePage/markmapUiHelpers'

const getProgressMessageForTask = (task: Task, noteTaskId: string): ConversationMessage | undefined =>
  (task.messages || []).find((message) =>
    message.message_type === 'note_progress'
    && message.meta?.task_id === noteTaskId,
  )

export const useTaskPolling = (interval = 3000, enabled = true) => {
  const tasks = useTaskStore(state => state.tasks)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)

  const tasksRef = useRef(tasks)

  // 每次 tasks 更新，把最新的 tasks 同步进去
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  useEffect(() => {
    if (!enabled) return

    const timer = setInterval(async () => {
      const pendingTasks = tasksRef.current.filter(
        task => !['SUCCESS', 'FAILED', 'CANCELED', 'NOT_FOUND'].includes(task.status)
      )

      // 无活跃任务时跳过轮询
      if (pendingTasks.length === 0) return

      for (const task of pendingTasks) {
        const noteTaskIds = task.pendingNoteTaskIds?.length
          ? task.pendingNoteTaskIds
          : task.linkedNoteTaskId
          ? [task.linkedNoteTaskId]
          : [task.id]

        for (const noteTaskId of noteTaskIds) {
          try {
          const res = await get_task_status(noteTaskId)
          const { status, message } = res
          const nextStatus = status as TaskStatus
          const progressMessage = getProgressMessageForTask(task, noteTaskId)
          const nextMessage = message || ''
          const nextAttemptId = res.attempt_id || ''
          const currentAttemptId = progressMessage?.meta?.attempt_id || ''
          const nextStageTimings = res.stage_timings || {}
          const currentStageTimings = progressMessage?.meta?.stage_timings || {}
          const nextCollectorTimings = res.collector_timings || {}
          const currentCollectorTimings = progressMessage?.meta?.collector_timings || {}
          const shouldUpdate =
            Boolean(nextStatus)
            && (
              nextStatus !== progressMessage?.status?.toUpperCase()
              || nextMessage !== (progressMessage?.meta?.detail || progressMessage?.content || '')
              || nextAttemptId !== currentAttemptId
              || JSON.stringify(nextStageTimings) !== JSON.stringify(currentStageTimings)
              || JSON.stringify(nextCollectorTimings) !== JSON.stringify(currentCollectorTimings)
            )

          if (shouldUpdate) {
            const taskStatusMeta = {
              taskId: res.task_id || noteTaskId,
              currentStep: nextStatus,
              attemptId: nextAttemptId,
              attempt: res.attempt,
              sourceUrl: res.source_url,
              extras: res.extras,
              stageTimings: nextStageTimings,
              collectorTimings: nextCollectorTimings,
              stageStartedAt: res.stage_started_at,
              updatedAt: res.updated_at,
            }
            if (nextStatus === 'SUCCESS') {
              const { markdown, transcript, audio_meta } = res.result || {}
              toast.success('笔记生成成功')
              updateTaskContent(task.id, {
                status: nextStatus,
                message,
                markdown,
                transcript,
                audioMeta: audio_meta,
                documentTaskId: res.task_id || noteTaskId,
                taskStatusMeta,
              })
            } else if (nextStatus === 'FAILED' || nextStatus === 'CANCELED' || nextStatus === 'NOT_FOUND') {
              updateTaskContent(task.id, { status: nextStatus, message, documentTaskId: res.task_id || noteTaskId, taskStatusMeta })
              console.warn(`⚠️ 任务 ${task.id} 失败`)
            } else {
              updateTaskContent(task.id, { status: nextStatus, message, documentTaskId: res.task_id || noteTaskId, taskStatusMeta })
              if (message && message !== (progressMessage?.meta?.detail || progressMessage?.content) && shouldShowTaskStatusToast(nextStatus)) {
                toast(message)
              }
            }
          }
          } catch (e) {
            console.error('❌ 任务轮询失败：', e)
            if (task.message !== '任务状态同步异常，稍后将自动重试') {
              updateTaskContent(task.id, {
                message: '任务状态同步异常，稍后将自动重试',
                documentTaskId: noteTaskId,
              })
            }
          }
        }
      }
    }, interval)

    return () => clearInterval(timer)
  }, [interval, enabled, updateTaskContent])
}
