<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { RunHistoryEntry } from '../types'

const props = defineProps<{ module: 'dedup' | 'searchmove' }>()

const router = useRouter()
const route = useRoute()
const runs = ref<RunHistoryEntry[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const busyId = ref<number | null>(null)

const modeOptions = computed(() =>
  props.module === 'searchmove'
    ? [
        { label: 'Test (Find only)', value: 'test' },
        { label: 'Move', value: 'move' },
        { label: 'Copy', value: 'copy' },
        { label: 'Delete', value: 'delete' },
      ]
    : [
        { label: 'Find only', value: 'f' },
        { label: 'Move', value: 'm' },
      ]
)

const targetRoute = computed(() => (props.module === 'searchmove' ? '/searchmove' : '/'))
const storageKey = computed(() =>
  props.module === 'searchmove' ? 'avior-searchmove-job-id' : 'avior-dedup-job-id'
)
const title = computed(() => (props.module === 'searchmove' ? 'Search & Move History' : 'Dedup History'))

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(`/api/history?module=${props.module}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    runs.value = (await res.json()).runs
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function rerun(run: RunHistoryEntry, mode: string) {
  busyId.value = run.id
  error.value = null
  try {
    const res = await fetch(`/api/history/${run.id}/rerun`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    sessionStorage.setItem(storageKey.value, data.job_id)
    router.push(targetRoute.value)
  } catch (e: any) {
    error.value = e.message
  } finally {
    busyId.value = null
  }
}

function param(run: RunHistoryEntry, key: string): string {
  const value = (run.params as Record<string, unknown>)?.[key]
  return typeof value === 'string' ? value : ''
}

function sourceOf(run: RunHistoryEntry): string {
  return param(run, 'source')
}

function targetOf(run: RunHistoryEntry): string {
  return param(run, 'target') || param(run, 'dest')
}

function formatParams(run: RunHistoryEntry): string {
  const p = run.params as Record<string, unknown> | null
  if (!p) return ''
  return Object.entries(p)
    .filter(([, v]) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0))
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(',') : String(v)}`)
    .join(' ')
}

function summaryText(run: RunHistoryEntry): string {
  const s = run.summary as Record<string, unknown> | null
  if (!s) return run.status === 'running' ? 'running…' : ''
  if (typeof s.error === 'string') return s.error
  const matched = s.files_matched
  const scanned = s.files_scanned
  const groups = s.groups_found
  if (matched !== undefined) return `${matched} matches / ${scanned} scanned`
  if (groups !== undefined) return `${groups} groups / ${scanned} scanned`
  return ''
}

function statusColor(status: string): string {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'cancelled') return 'warning'
  return 'info'
}

// Reload whenever the history view is entered or the module changes. Both
// history routes reuse this component, so onMounted alone would keep showing
// the previously loaded module's runs.
watch(
  () => [route.path, props.module],
  () => { load() },
  { immediate: true }
)
</script>

<template>
  <v-card>
    <v-card-item>
      <v-card-title class="text-none">{{ title }}</v-card-title>
      <v-card-subtitle>Past runs with their parameters. Repeat a run with the same parameters, choosing Test (Find only) or Move.</v-card-subtitle>
    </v-card-item>
    <v-divider />

    <v-card-text>
      <v-alert v-if="error" type="error" variant="tonal" class="mb-3">{{ error }}</v-alert>

      <div class="d-flex align-center mb-3">
        <v-btn size="small" variant="tonal" prepend-icon="mdi-refresh" @click="load" :loading="loading">
          Refresh
        </v-btn>
      </div>

      <div v-if="!loading && runs.length === 0" class="text-medium-emphasis">
        No runs yet.
      </div>

      <v-table v-else density="compact">
        <thead>
          <tr>
            <th>ID</th>
            <th>Mode</th>
            <th>Source</th>
            <th>Target</th>
            <th>Status</th>
            <th>Created</th>
            <th>Result</th>
            <th>Parameters</th>
            <th>Repeat</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in runs" :key="run.id">
            <td>#{{ run.id }}</td>
            <td>{{ run.mode }}</td>
            <td class="text-truncate" style="max-width: 260px;">{{ sourceOf(run) }}</td>
            <td class="text-truncate" style="max-width: 260px;">{{ targetOf(run) }}</td>
            <td>
              <v-chip :color="statusColor(run.status)" size="small" variant="tonal">{{ run.status }}</v-chip>
            </td>
            <td class="text-no-wrap">{{ run.created_at }}</td>
            <td>{{ summaryText(run) }}</td>
            <td>
              <code class="params-cell">{{ formatParams(run) }}</code>
            </td>
            <td>
              <v-menu>
                <template #activator="{ props: menuProps }">
                  <v-btn
                    v-bind="menuProps"
                    size="small"
                    variant="tonal"
                    prepend-icon="mdi-repeat"
                    :loading="busyId === run.id"
                  >
                    Repeat
                  </v-btn>
                </template>
                <v-list density="compact">
                  <v-list-item
                    v-for="opt in modeOptions"
                    :key="opt.value"
                    :title="opt.label"
                    @click="rerun(run, opt.value)"
                  />
                </v-list>
              </v-menu>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.params-cell {
  display: block;
  max-width: 480px;
  white-space: normal;
  word-break: break-word;
  font-size: 0.75rem;
  line-height: 1.35;
  color: rgba(var(--v-theme-on-surface), 0.8);
}
</style>
