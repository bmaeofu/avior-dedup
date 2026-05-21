<script setup lang="ts">
import { computed } from 'vue'
import type { ProgressSnapshot } from '../types'

const props = defineProps<{
  progress: ProgressSnapshot | null
  state: string
}>()

const emit = defineEmits<{
  cancel: []
}>()

const phaseColor = computed(() => {
  switch (props.progress?.phase) {
    case 'scanning': return 'info'
    case 'planning': return 'warning'
    case 'executing': return 'success'
    default: return 'grey'
  }
})

const phaseLabel = computed(() => {
  switch (props.progress?.phase) {
    case 'scanning': return 'Scanning files'
    case 'planning': return 'Building move plan'
    case 'executing': return 'Executing moves'
    default: return 'Starting...'
  }
})

const progressPercent = computed(() => {
  if (!props.progress) return 0
  const p = props.progress

  // Scanning: 0% – 50%
  if (p.phase === 'scanning') {
    if (p.dirs_total <= 0) return 0
    return Math.round((p.dirs_completed / p.dirs_total) * 50)
  }

  // Planning: 50% – 75%
  if (p.phase === 'planning') {
    if (p.groups_found <= 0) return 50
    return 50 + Math.round((p.files_planned / p.groups_found) * 25)
  }

  // Executing: 75% – 100%
  if (p.phase === 'executing') {
    if (p.total_files_to_move <= 0) return 75
    return 75 + Math.round((p.files_moved / p.total_files_to_move) * 25)
  }

  return 0
})

const isIndeterminate = computed(() => {
  if (!props.progress) return true
  if (props.progress.phase === 'scanning') return props.progress.dirs_total === 0
  return false
})

const truncatedDir = computed(() => {
  const dir = props.progress?.current_dir
  if (!dir) return ''
  return dir.length > 100 ? '...' + dir.slice(-97) : dir
})

const scanLabel = computed(() => {
  if (!props.progress || props.progress.phase !== 'scanning') return ''
  if (props.progress.dirs_total > 0) {
    return `${props.progress.dirs_completed} / ${props.progress.dirs_total} directories`
  }
  return ''
})
</script>

<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <v-chip :color="phaseColor" size="small" class="mr-3">
        {{ phaseLabel }}
      </v-chip>
      <span v-if="scanLabel" class="text-body-2 text-medium-emphasis ml-2">{{ scanLabel }}</span>
      <v-spacer />
      <v-btn
        color="error"
        variant="outlined"
        size="small"
        prepend-icon="mdi-stop"
        @click="emit('cancel')"
      >
        Cancel
      </v-btn>
    </v-card-title>

    <v-card-text>
      <v-progress-linear
        :model-value="isIndeterminate ? undefined : progressPercent"
        :indeterminate="isIndeterminate"
        :color="phaseColor"
        height="8"
        rounded
        class="mb-4"
      />

      <v-row dense v-if="progress">
        <v-col cols="6" md="3">
          <div class="text-caption text-medium-emphasis">Files scanned</div>
          <div class="text-h6">{{ progress.files_scanned.toLocaleString() }}</div>
        </v-col>
        <v-col cols="6" md="3">
          <div class="text-caption text-medium-emphasis">Groups found</div>
          <div class="text-h6">{{ progress.groups_found.toLocaleString() }}</div>
        </v-col>
        <v-col cols="6" md="3">
          <div class="text-caption text-medium-emphasis">Groups planned</div>
          <div class="text-h6">{{ progress.files_planned.toLocaleString() }} / {{ progress.groups_found.toLocaleString() }}</div>
        </v-col>
        <v-col cols="6" md="3">
          <div class="text-caption text-medium-emphasis">Files moved</div>
          <div class="text-h6">{{ progress.files_moved.toLocaleString() }} / {{ progress.total_files_to_move.toLocaleString() }}</div>
        </v-col>
      </v-row>

      <v-alert
        v-if="truncatedDir"
        type="info"
        density="compact"
        variant="tonal"
        class="mt-3"
      >
        <span class="text-body-2 font-weight-medium" style="font-family: monospace">{{ truncatedDir }}</span>
      </v-alert>
    </v-card-text>
  </v-card>
</template>
