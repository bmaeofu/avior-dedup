<script setup lang="ts">
import { computed } from 'vue'
import type { JobResult } from '../types'

const props = defineProps<{
  result: JobResult
  error?: string | null
}>()

const emit = defineEmits<{
  newJob: []
}>()

const actionLabels: Record<string, { label: string; icon: string; color: string }> = {
  KEEP:                              { label: 'Kept',                             icon: 'mdi-check-circle',      color: 'green' },
  KEEP_MC:                           { label: 'Kept (multichannel)',              icon: 'mdi-check-circle',      color: 'green-darken-2' },
  KEEP_WITH_ERRORS:                  { label: 'Kept (with errors)',               icon: 'mdi-check-circle',      color: 'green-lighten-1' },
  KEEP_MC_WITH_ERRORS:               { label: 'Kept MC (with errors)',            icon: 'mdi-check-circle',      color: 'green-darken-1' },
  KEEP_WITH_LONGER_DURATION:         { label: 'Kept (longer duration)',           icon: 'mdi-check-circle',      color: 'green-lighten-1' },
  KEEP_MC_WITH_LONGER_DURATION:      { label: 'Kept MC (longer duration)',        icon: 'mdi-check-circle',      color: 'green-darken-1' },
  KEEP_WITH_SHORTER_DURATION:        { label: 'Kept (shorter duration)',          icon: 'mdi-check-circle',      color: 'green-lighten-1' },
  KEEP_MC_WITH_SHORTER_DURATION:     { label: 'Kept MC (shorter duration)',       icon: 'mdi-check-circle',      color: 'green-darken-1' },
  DUPLICATE:                         { label: 'Duplicate',                        icon: 'mdi-content-copy',      color: 'orange' },
  DUPLICATE_WITH_ERRORS:             { label: 'Duplicate with errors',            icon: 'mdi-alert-circle',      color: 'red' },
  DUPLICATE_WITH_ERRORS_MC:          { label: 'Duplicate with errors (MC)',       icon: 'mdi-alert-circle',      color: 'red-darken-2' },
  DUPLICATE_WITH_LONGER_DURATION:    { label: 'Duplicate (longer duration)',      icon: 'mdi-content-copy',      color: 'orange-darken-2' },
  DUPLICATE_WITH_SHORTER_DURATION:   { label: 'Duplicate (shorter duration)',     icon: 'mdi-content-copy',      color: 'orange-darken-2' },
  NO_VIDEO:                          { label: 'No video found',                   icon: 'mdi-video-off',         color: 'grey' },
  SKIP_EXISTS:                       { label: 'Skipped (already exists)',          icon: 'mdi-skip-next-circle',  color: 'blue-grey' },
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function formatAction(key: string) {
  return actionLabels[key] ?? { label: key.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase()), icon: 'mdi-help-circle', color: 'grey' }
}

const tableRows = computed(() => {
  const counts = props.result.action_counts
  const sizes = props.result.action_sizes ?? {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  return Object.entries(counts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([action, count]) => ({
      ...formatAction(action),
      action,
      count,
      size: sizes[action] ?? 0,
      percentage: total > 0 ? ((count / total) * 100).toFixed(1) : '0.0',
    }))
})

const totalFiles = computed(() =>
  Object.values(props.result.action_counts).reduce((a, b) => a + b, 0)
)

const totalSize = computed(() =>
  Object.values(props.result.action_sizes ?? {}).reduce((a, b) => a + b, 0)
)
</script>

<template>
  <v-card>
    <v-card-title>
      <v-alert
        v-if="!error"
        type="success"
        density="compact"
        variant="tonal"
        class="mb-2"
      >
        Job completed &mdash; {{ result.files_scanned.toLocaleString() }} files scanned, {{ result.groups_found }} duplicate groups found
      </v-alert>
      <v-alert
        v-else
        type="error"
        density="compact"
        variant="tonal"
        class="mb-2"
      >
        Job failed: {{ error }}
      </v-alert>
    </v-card-title>

    <v-card-text>
      <v-table density="compact">
        <thead>
          <tr>
            <th>Action</th>
            <th class="text-right">Count</th>
            <th class="text-right">%</th>
            <th class="text-right">Size</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.action">
            <td>
              <v-chip :color="row.color" size="small" label :prepend-icon="row.icon">{{ row.label }}</v-chip>
            </td>
            <td class="text-right">{{ row.count.toLocaleString() }}</td>
            <td class="text-right">{{ row.percentage }}%</td>
            <td class="text-right">{{ formatSize(row.size) }}</td>
          </tr>
          <tr class="font-weight-bold">
            <td>TOTAL</td>
            <td class="text-right">{{ totalFiles.toLocaleString() }}</td>
            <td class="text-right">100%</td>
            <td class="text-right">{{ formatSize(totalSize) }}</td>
          </tr>
        </tbody>
      </v-table>

      <v-alert
        v-if="result.log_path"
        type="info"
        density="compact"
        variant="tonal"
        class="mt-4"
      >
        Log file: <code>{{ result.log_path }}</code>
        <div v-if="result.timing_path" class="mt-2">Timing: <code>{{ result.timing_path }}</code></div>
      </v-alert>
    </v-card-text>

    <v-card-actions>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-reload" @click="emit('newJob')">
        New Job
      </v-btn>
    </v-card-actions>
  </v-card>
</template>
