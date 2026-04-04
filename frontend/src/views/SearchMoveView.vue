<script setup lang="ts">
import { useSearchMoveJob } from '../composables/useSearchMoveJob'
import SearchMoveForm from '../components/SearchMoveForm.vue'
import SearchMoveProgress from '../components/SearchMoveProgress.vue'
import SearchMoveResults from '../components/SearchMoveResults.vue'
import type { SearchMoveRequest } from '../types'

const { state, progress, result, error, isRunning, start, cancel, reset } = useSearchMoveJob()

function onStart(req: SearchMoveRequest) {
  start(req)
}
</script>

<template>
  <SearchMoveForm v-if="state === 'idle'" @start="onStart" />

  <SearchMoveProgress v-else-if="isRunning" :progress="progress" @cancel="cancel" />

  <SearchMoveResults v-else-if="state === 'completed' && result" :result="result" @new-job="reset" />

  <v-card v-else-if="state === 'failed'">
    <v-card-text>
      <v-alert type="error" variant="tonal">
        Job failed: {{ error ?? 'Unknown error' }}
      </v-alert>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn color="primary" variant="tonal" @click="reset">Try Again</v-btn>
    </v-card-actions>
  </v-card>

  <v-card v-else-if="state === 'cancelled'">
    <v-card-text>
      <v-alert type="warning" variant="tonal">Job was cancelled.</v-alert>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn color="primary" variant="tonal" @click="reset">New Job</v-btn>
    </v-card-actions>
  </v-card>
</template>
