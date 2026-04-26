import { ref, computed, onMounted } from 'vue'
import type { ProgressSnapshot, SearchMoveRequest, SearchMoveResult, SearchMoveJobStatus } from '../types'

const STORAGE_KEY = 'avior-searchmove-job-id'

export function useSearchMoveJob() {
  const state = ref<'idle' | 'running' | 'completed' | 'failed' | 'cancelled'>('idle')
  const progress = ref<ProgressSnapshot | null>(null)
  const result = ref<SearchMoveResult | null>(null)
  const error = ref<string | null>(null)
  const jobId = ref<string | null>(null)

  const isRunning = computed(() => state.value === 'running')

  let ws: WebSocket | null = null
  let pollTimer: number | null = null

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function pollJobStatus(id: string) {
    try {
      const resp = await fetch(`/api/searchmove/jobs/${id}`)
      if (!resp.ok) return

      const data: SearchMoveJobStatus = await resp.json()
      state.value = data.state
      if (data.progress) progress.value = data.progress

      if (data.state !== 'running') {
        result.value = data.result ?? null
        error.value = data.error ?? null
        stopPolling()
        ws?.close()
      }
    } catch {
      // Keep running and try again on next tick.
    }
  }

  function startPolling(id: string) {
    stopPolling()
    pollJobStatus(id)
    pollTimer = window.setInterval(() => {
      void pollJobStatus(id)
    }, 250)
  }

  function connectWs(id: string) {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}/api/searchmove/ws/jobs/${id}`)

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      // JobStatus message (final): has 'state' field
      if (data.state) {
        state.value = data.state
        if (data.progress) progress.value = data.progress
        result.value = data.result ?? null
        error.value = data.error ?? null
        if (data.state !== 'running') {
          stopPolling()
          ws?.close()
        }
      // ProgressSnapshot message (interim): has 'phase' field
      } else if (data.phase !== undefined) {
        progress.value = data
      }
    }

    ws.onerror = () => {
      // Polling fallback continues to provide progress.
    }

    ws.onclose = () => {
      ws = null
    }
  }

  async function start(req: SearchMoveRequest) {
    const resp = await fetch('/api/searchmove/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    })
    if (!resp.ok) {
      state.value = 'failed'
      error.value = `Failed to start job: ${resp.statusText}`
      return
    }
    const body = await resp.json()
    jobId.value = body.job_id
    sessionStorage.setItem(STORAGE_KEY, body.job_id)
    state.value = 'running'
    progress.value = null
    result.value = null
    error.value = null
    connectWs(body.job_id)
    startPolling(body.job_id)
  }

  async function cancel() {
    if (!jobId.value) return
    await fetch(`/api/searchmove/jobs/${jobId.value}`, { method: 'DELETE' })
  }

  function reset() {
    state.value = 'idle'
    progress.value = null
    result.value = null
    error.value = null
    jobId.value = null
    sessionStorage.removeItem(STORAGE_KEY)
    stopPolling()
    ws?.close()
    ws = null
  }

  async function resumeIfNeeded() {
    const savedId = sessionStorage.getItem(STORAGE_KEY)
    if (!savedId) return

    try {
      const resp = await fetch(`/api/searchmove/jobs/${savedId}`)
      if (!resp.ok) {
        sessionStorage.removeItem(STORAGE_KEY)
        return
      }
      const data: SearchMoveJobStatus = await resp.json()
      jobId.value = savedId

      if (data.state === 'running') {
        state.value = 'running'
        progress.value = data.progress
        connectWs(savedId)
        startPolling(savedId)
      } else {
        state.value = data.state
        progress.value = data.progress
        result.value = data.result ?? null
        error.value = data.error ?? null
      }
    } catch {
      sessionStorage.removeItem(STORAGE_KEY)
    }
  }

  onMounted(resumeIfNeeded)

  return { state, progress, result, error, jobId, isRunning, start, cancel, reset }
}
