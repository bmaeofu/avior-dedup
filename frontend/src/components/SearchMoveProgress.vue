<script setup lang="ts">
import { computed } from 'vue'
import type { ProgressSnapshot } from '../types'

const props = defineProps<{ progress: ProgressSnapshot | null }>()
const emit = defineEmits<{ cancel: [] }>()

const phase = computed(() => props.progress?.phase ?? '')

const phaseLabel = computed(() => {
  switch (phase.value) {
    case 'scanning': return 'Scanning directories'
    case 'searching': return 'Searching files'
    case 'executing': return 'Executing actions'
    default: return 'Starting...'
  }
})

const phaseColor = computed(() => {
  switch (phase.value) {
    case 'scanning': return 'info'
    case 'searching': return 'warning'
    case 'executing': return 'success'
    default: return 'grey'
  }
})

const currentLabel = computed(() => {
  if (phase.value === 'executing' || phase.value === 'searching') return 'Current File'
  return 'Current Directory'
})

const currentValue = computed(() => {
  if (phase.value === 'executing' || phase.value === 'searching') {
    return props.progress?.current_file ?? '—'
  }
  return props.progress?.current_dir ?? '—'
})

const percent = computed(() => {
  const p = props.progress
  if (!p) return 0

  if (phase.value === 'scanning') return 10
  if (phase.value === 'searching') {
    const total = p.dirs_total || 1
    const done = p.files_scanned || 0
    return 10 + (done / total) * 60
  }
  if (phase.value === 'executing') {
    const total = p.total_files_to_move || 1
    const done = p.files_moved || 0
    return 70 + (done / total) * 30
  }
  return 0
})

const isIndeterminate = computed(() => phase.value === 'scanning')
</script>

<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <v-chip :color="phaseColor" size="small" class="mr-2">{{ phaseLabel }}</v-chip>
      <v-spacer />
      <v-btn color="error" variant="tonal" size="small" @click="emit('cancel')">Cancel</v-btn>
    </v-card-title>

    <v-card-text>
      <v-progress-linear
        :model-value="percent"
        :indeterminate="isIndeterminate"
        :color="phaseColor"
        height="8"
        rounded
        class="mb-3"
      />

      <v-row dense>
        <v-col cols="6" md="3">
          <div class="text-caption text-medium-emphasis">Files Scanned</div>
          <div class="text-h6">{{ progress?.files_scanned?.toLocaleString() ?? 0 }}</div>
        </v-col>
        <v-col cols="6" md="3">
          <div class="text-caption text-medium-emphasis">Matches Found</div>
          <div class="text-h6">{{ progress?.groups_found?.toLocaleString() ?? 0 }}</div>
        </v-col>
        <v-col cols="6" md="3">
          <div class="text-caption text-medium-emphasis">Files Acted</div>
          <div class="text-h6">{{ progress?.files_moved?.toLocaleString() ?? 0 }} / {{ progress?.total_files_to_move?.toLocaleString() ?? 0 }}</div>
        </v-col>
        <v-col cols="6" md="3">
          <div class="text-caption text-medium-emphasis">{{ currentLabel }}</div>
          <div class="text-body-2 text-truncate">{{ currentValue }}</div>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>
