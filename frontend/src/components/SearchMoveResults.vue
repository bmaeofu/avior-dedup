<script setup lang="ts">
import { computed } from 'vue'
import type { SearchMoveResult } from '../types'

const props = defineProps<{ result: SearchMoveResult }>()
const emit = defineEmits<{ newJob: [] }>()

const actionRows = computed(() =>
  Object.entries(props.result.action_counts).map(([action, count]) => ({
    action,
    count,
  }))
)

const matchHeaders = [
  { title: 'File', key: 'file_path' },
  { title: 'Expression', key: 'matched_expression' },
  { title: 'Found', key: 'found_values' },
]
</script>

<template>
  <v-card>
    <v-card-item>
      <v-card-title class="text-none">
        <v-alert type="success" variant="tonal" density="compact" class="mb-0">
          Search & Move completed — {{ result.files_matched }} matches from {{ result.files_scanned.toLocaleString() }} files
        </v-alert>
      </v-card-title>
    </v-card-item>

    <v-card-text>
      <!-- Action summary -->
      <v-table v-if="actionRows.length > 0" density="compact" class="mb-4">
        <thead>
          <tr>
            <th>Action</th>
            <th class="text-right">Count</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in actionRows" :key="row.action">
            <td>{{ row.action }}</td>
            <td class="text-right">{{ row.count.toLocaleString() }}</td>
          </tr>
        </tbody>
      </v-table>

      <!-- Match details -->
      <div v-if="result.matches.length > 0">
        <div class="text-subtitle-2 text-medium-emphasis mb-2">Matched Files</div>
        <v-data-table
          :headers="matchHeaders"
          :items="result.matches"
          density="compact"
          :items-per-page="25"
          class="elevation-1"
        >
          <template #item.file_path="{ value }">
            <span class="text-body-2" style="word-break: break-all;">
              {{ value }}
            </span>
          </template>
          <template #item.matched_expression="{ value }">
            <code class="text-caption">{{ value }}</code>
          </template>
          <template #item.found_values="{ value }">
            <code class="text-caption">{{ value }}</code>
          </template>
        </v-data-table>
      </div>

      <v-alert
        v-if="result.log_path"
        type="info"
        variant="tonal"
        density="compact"
        class="mt-3"
      >
        Log: {{ result.log_path }}
        <div v-if="result.timing_path" class="mt-2">Timing: <code>{{ result.timing_path }}</code></div>
      </v-alert>
    </v-card-text>

    <v-divider />
    <v-card-actions>
      <v-spacer />
      <v-btn color="primary" variant="tonal" class="text-none" @click="emit('newJob')">New Job</v-btn>
    </v-card-actions>
  </v-card>
</template>
