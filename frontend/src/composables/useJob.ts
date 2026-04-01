import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { JobRequest, ProgressSnapshot, JobResult } from '../types'

const STORAGE_KEY = 'avior-dedup-job-id'

export function useJob() {
  const jobId = ref<string | null>(null)
  const state = ref<string>('idle')
  const progress = ref<ProgressSnapshot | null>(null)
  const result = ref<JobResult | null>(null)
  const error = ref<string | null>(null)

  let ws: WebSocket | null = null

  const isRunning = computed(() =>
    ['pending', 'scanning', 'planning', 'executing', 'running'].includes(state.value)
  )

  function connectWebSocket(id: string) {
    ws?.close()
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}/api/ws/jobs/${id}`)

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)

      if (msg.state) {
        state.value = msg.state
        if (msg.progress) progress.value = msg.progress
        if (msg.result) result.value = msg.result
        if (msg.error) error.value = msg.error
        // Clear storage when job is done
        if (!isRunning.value) {
          sessionStorage.removeItem(STORAGE_KEY)
        }
      } else if (msg.phase !== undefined) {
        progress.value = msg
        state.value = msg.phase || state.value
      }
    }

    ws.onclose = () => {
      ws = null
    }

    ws.onerror = () => {
      error.value = 'WebSocket connection error'
      ws?.close()
    }
  }

  async function resumeJob(id: string) {
    try {
      const res = await fetch(`/api/jobs/${id}`)
      if (!res.ok) {
        sessionStorage.removeItem(STORAGE_KEY)
        return
      }
      const status = await res.json()
      jobId.value = id
      state.value = status.state
      if (status.progress) progress.value = status.progress
      if (status.result) result.value = status.result
      if (status.error) error.value = status.error

      if (['pending', 'scanning', 'planning', 'executing', 'running'].includes(status.state)) {
        connectWebSocket(id)
      } else {
        sessionStorage.removeItem(STORAGE_KEY)
      }
    } catch {
      sessionStorage.removeItem(STORAGE_KEY)
    }
  }

  onMounted(() => {
    const savedId = sessionStorage.getItem(STORAGE_KEY)
    if (savedId) {
      resumeJob(savedId)
    }
  })

  async function startJob(request: JobRequest) {
    state.value = 'pending'
    progress.value = null
    result.value = null
    error.value = null

    try {
      const res = await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      jobId.value = data.job_id
      sessionStorage.setItem(STORAGE_KEY, data.job_id)
      connectWebSocket(data.job_id)
    } catch (e: any) {
      state.value = 'failed'
      error.value = e.message
    }
  }

  async function cancelJob() {
    if (!jobId.value) return
    try {
      await fetch(`/api/jobs/${jobId.value}`, { method: 'DELETE' })
    } catch {
      // best effort
    }
  }

  function reset() {
    ws?.close()
    ws = null
    sessionStorage.removeItem(STORAGE_KEY)
    jobId.value = null
    state.value = 'idle'
    progress.value = null
    result.value = null
    error.value = null
  }

  onUnmounted(() => {
    ws?.close()
  })

  return { jobId, state, progress, result, error, isRunning, startJob, cancelJob, reset }
}
