<script setup lang="ts">
import { computed } from 'vue'
import type { SearchMoveResult } from '../types'

const props = defineProps<{ result: SearchMoveResult }>()
const emit = defineEmits<{ newJob: [] }>()

const tableRows = computed(() =>
  Object.entries(props.result.action_counts).map(([action, count]) => ({
    action,
    count,
  }))
)
</script>

<template>
  <v-card>
    <v-card-title>
      <v-alert type="success" variant="tonal" density="compact" class="mb-0">
        Search & Move completed — {{ result.files_matched }} matches found from {{ result.files_scanned.toLocaleString() }} files scanned
      </v-alert>
    </v-card-title>

    <v-card-text>
      <v-table v-if="tableRows.length > 0" density="compact">
        <thead>
          <tr>
            <th>Action</th>
            <th class="text-right">Count</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.action">
            <td>{{ row.action }}</td>
            <td class="text-right">{{ row.count.toLocaleString() }}</td>
          </tr>
        </tbody>
      </v-table>

      <v-alert
        v-if="result.log_path"
        type="info"
        variant="tonal"
        density="compact"
        class="mt-3"
      >
        Log: {{ result.log_path }}
      </v-alert>
    </v-card-text>

    <v-card-actions>
      <v-spacer />
      <v-btn color="primary" variant="tonal" @click="emit('newJob')">New Job</v-btn>
    </v-card-actions>
  </v-card>
</template>
