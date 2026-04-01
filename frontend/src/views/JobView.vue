<script setup lang="ts">
import { useJob } from '../composables/useJob'
import type { JobRequest } from '../types'
import JobForm from '../components/JobForm.vue'
import ProgressPanel from '../components/ProgressPanel.vue'
import ResultsPanel from '../components/ResultsPanel.vue'

const { state, progress, result, error, isRunning, startJob, cancelJob, reset } = useJob()

function handleStart(request: JobRequest) {
  startJob(request)
}
</script>

<template>
  <div>
    <JobForm
      v-if="state === 'idle'"
      @start="handleStart"
    />

    <ProgressPanel
      v-else-if="isRunning"
      :progress="progress"
      :state="state"
      @cancel="cancelJob"
    />

    <ResultsPanel
      v-else-if="state === 'completed' && result"
      :result="result"
      :error="error"
      @new-job="reset"
    />

    <v-card v-else-if="state === 'failed'">
      <v-card-text>
        <v-alert type="error" variant="tonal">
          {{ error || 'Job failed' }}
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" prepend-icon="mdi-reload" @click="reset">New Job</v-btn>
      </v-card-actions>
    </v-card>

    <v-card v-else-if="state === 'cancelled'">
      <v-card-text>
        <v-alert type="warning" variant="tonal">Job was cancelled.</v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" prepend-icon="mdi-reload" @click="reset">New Job</v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>
