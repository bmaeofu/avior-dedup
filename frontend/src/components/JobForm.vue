<script setup lang="ts">
import { reactive, computed, ref, onMounted } from 'vue'
import type { JobRequest } from '../types'
import ChipListEditor from './ChipListEditor.vue'

const emit = defineEmits<{
  start: [request: JobRequest]
}>()

const sourceSuggestions = ref<string[]>([])
const targetSuggestions = ref<string[]>([])

onMounted(async () => {
  try {
    const res = await fetch('/api/config/path_suggestions')
    if (res.ok) {
      const data = await res.json()
      sourceSuggestions.value = data.source_paths ?? []
      targetSuggestions.value = data.target_paths ?? []
    }
  } catch {
    // suggestions are optional, ignore errors
  }
})

const form = reactive<JobRequest>({
  mode: 'f',
  source: '',
  target: '',
  logname: 'dedup_log.txt',
  duptype: 'case',
  prefer_errors: false,
  error_target: null,
  novideo_target: null,
  max_errors_when_mc: 3,
  semantic_prefixes: ['terra\\s*x\\s*-\\s*'],
  remove_episode_nos: false,
})

const canSubmit = computed(() => form.source.trim() !== '' && form.target.trim() !== '')

const modeItems = [
  { title: 'Find Only', value: 'f' },
  { title: 'Move', value: 'm' },
]

const dupTypeItems = [
  { title: 'Case-insensitive', value: 'case' },
  { title: 'Exact name', value: 'exact' },
  { title: 'Semantic', value: 'semantic' },
  { title: 'Case + Exact', value: 'both' },
  { title: 'All types', value: 'all' },
]

function submit() {
  emit('start', { ...form })
}
</script>

<template>
  <v-card>
    <v-card-title>Dedup Job</v-card-title>
    <v-card-text>
      <v-row dense>
        <v-col cols="12" md="6">
          <v-btn-toggle v-model="form.mode" mandatory color="primary" density="compact" class="mb-4">
            <v-btn v-for="item in modeItems" :key="item.value" :value="item.value">
              {{ item.title }}
            </v-btn>
          </v-btn-toggle>
        </v-col>
        <v-col cols="12" md="6">
          <v-select
            v-model="form.duptype"
            :items="dupTypeItems"
            label="Duplicate type"
            density="compact"
            variant="outlined"
          />
        </v-col>
      </v-row>

      <v-row dense>
        <v-col cols="12" md="6">
          <v-combobox
            v-model="form.source"
            :items="sourceSuggestions"
            label="Source directory"
            density="compact"
            variant="outlined"
            prepend-inner-icon="mdi-folder"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-combobox
            v-model="form.target"
            :items="targetSuggestions"
            label="Target directory"
            density="compact"
            variant="outlined"
            prepend-inner-icon="mdi-folder-move"
            hide-details
          />
        </v-col>
      </v-row>

      <v-row dense>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.logname"
            label="Log filename"
            density="compact"
            variant="outlined"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.error_target"
            label="Error target (optional)"
            density="compact"
            variant="outlined"
            clearable
            hint="Leave empty for <target>/errors"
            persistent-hint
          >
            <template #append-inner>
              <v-tooltip location="top" max-width="300">
                <template #activator="{ props: tp }">
                  <v-icon v-bind="tp" size="small">mdi-help-circle-outline</v-icon>
                </template>
                Directory where duplicates with encoding errors are moved to. When the best recording is kept, inferior copies that have errors in their .log files end up here instead of the main target.
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.novideo_target"
            label="No-video target (optional)"
            density="compact"
            variant="outlined"
            clearable
            hint="Leave empty for <target>/no_video"
            persistent-hint
          >
            <template #append-inner>
              <v-tooltip location="top" max-width="300">
                <template #activator="{ props: tp }">
                  <v-icon v-bind="tp" size="small">mdi-help-circle-outline</v-icon>
                </template>
                Directory where metadata files (logs, nfo, images) with no corresponding video file are moved to.
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
      </v-row>

      <v-row dense>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="form.max_errors_when_mc"
            label="Max errors (multichannel)"
            type="number"
            density="compact"
            variant="outlined"
            min="0"
          >
            <template #append-inner>
              <v-tooltip location="top" max-width="300">
                <template #activator="{ props: tp }">
                  <v-icon v-bind="tp" size="small">mdi-help-circle-outline</v-icon>
                </template>
                Maximum number of encoding errors allowed for a multichannel (AC3 5.x) recording to still be considered a good copy. Recordings exceeding this are treated as error duplicates.
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
        <v-col cols="12" md="4">
          <v-checkbox
            v-model="form.prefer_errors"
            label="Prefer fewer errors"
            density="compact"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-checkbox
            v-model="form.remove_episode_nos"
            label="Remove episode numbers"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>

      <v-row dense>
        <v-col cols="12">
          <ChipListEditor
            v-model="form.semantic_prefixes"
            label="Semantic prefixes (regex patterns to strip)"
          />
        </v-col>
      </v-row>
    </v-card-text>
    <v-card-actions>
      <v-spacer />
      <v-btn
        color="primary"
        size="large"
        :disabled="!canSubmit"
        prepend-icon="mdi-play"
        @click="submit"
      >
        Start Scan
      </v-btn>
    </v-card-actions>
  </v-card>
</template>
