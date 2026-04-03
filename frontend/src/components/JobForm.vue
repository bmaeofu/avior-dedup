<script setup lang="ts">
import { reactive, computed, ref, onMounted } from 'vue'
import type { JobRequest, SelectionPriority } from '../types'
import ListEditor from './ListEditor.vue'

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
  max_duration_diff_longer: 600,
  max_duration_diff_shorter: 120,
  selection_priorities: ['multichannel', 'fewer_errors', 'closest_duration'] as SelectionPriority[],
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

const priorityLabels: Record<SelectionPriority, string> = {
  multichannel: 'Multichannel',
  fewer_errors: 'Fewer errors',
  closest_duration: 'Closest EPG duration',
}

function movePriority(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= form.selection_priorities.length) return
  const arr = [...form.selection_priorities]
  ;[arr[index], arr[target]] = [arr[target], arr[index]]
  form.selection_priorities = arr
}

function submit() {
  emit('start', { ...form })
}
</script>

<template>
  <v-card>
    <v-card-item>
      <v-card-title class="text-none">Dedup Scan</v-card-title>
    </v-card-item>
    <v-divider />
    <v-card-text>
      <!-- Directories -->
      <div class="text-subtitle-2 text-medium-emphasis mb-2">Directories</div>
      <v-row dense>
        <v-col cols="12" md="6">
          <v-combobox
            v-model="form.source"
            :items="sourceSuggestions"
            label="Source"
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
            label="Target"
            density="compact"
            variant="outlined"
            prepend-inner-icon="mdi-folder-move"
            hide-details
          />
        </v-col>
      </v-row>

      <v-divider class="my-4" />

      <!-- Scan settings -->
      <div class="text-subtitle-2 text-medium-emphasis mb-2">Scan settings</div>
      <v-row dense align="center">
        <v-col cols="12" md="4">
          <v-select
            v-model="form.duptype"
            :items="dupTypeItems"
            label="Duplicate type"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-btn-toggle v-model="form.mode" mandatory color="primary" density="compact">
            <v-btn v-for="item in modeItems" :key="item.value" :value="item.value" class="text-none">
              {{ item.title }}
            </v-btn>
          </v-btn-toggle>
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.logname"
            label="Log filename"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-col>
      </v-row>

      <v-divider class="my-4" />

      <!-- Error handling -->
      <div class="text-subtitle-2 text-medium-emphasis mb-2">Error handling</div>
      <v-row dense>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="form.max_errors_when_mc"
            label="Max errors (multichannel)"
            type="number"
            density="compact"
            variant="outlined"
            min="0"
            hide-details
          >
            <template #append-inner>
              <v-tooltip location="top" max-width="300">
                <template #activator="{ props: tp }">
                  <v-icon v-bind="tp" size="small">mdi-help-circle-outline</v-icon>
                </template>
                Maximum encoding errors allowed for a multichannel recording to still be considered good.
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="form.max_duration_diff_longer"
            label="Max duration +diff (sec)"
            type="number"
            density="compact"
            variant="outlined"
            min="0"
            hide-details
          >
            <template #append-inner>
              <v-tooltip location="top" max-width="300">
                <template #activator="{ props: tp }">
                  <v-icon v-bind="tp" size="small">mdi-help-circle-outline</v-icon>
                </template>
                Maximum allowed value for (video_duration - rec_duration) in seconds.
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="form.max_duration_diff_shorter"
            label="Max duration -diff (sec)"
            type="number"
            density="compact"
            variant="outlined"
            min="0"
            hide-details
          >
            <template #append-inner>
              <v-tooltip location="top" max-width="300">
                <template #activator="{ props: tp }">
                  <v-icon v-bind="tp" size="small">mdi-help-circle-outline</v-icon>
                </template>
                Maximum allowed value for (rec_duration - video_duration) in seconds.
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
      </v-row>
      <v-row dense class="mt-1">
        <v-col cols="12" md="6">
          <v-text-field
            v-model="form.error_target"
            label="Error target"
            density="compact"
            variant="outlined"
            clearable
            hide-details
            placeholder="Default: <target>/errors"
          >
            <template #append-inner>
              <v-tooltip location="top" max-width="300">
                <template #activator="{ props: tp }">
                  <v-icon v-bind="tp" size="small">mdi-help-circle-outline</v-icon>
                </template>
                Directory where duplicates with encoding errors are moved to.
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
        <v-col cols="12" md="6">
          <v-text-field
            v-model="form.novideo_target"
            label="No-video target"
            density="compact"
            variant="outlined"
            clearable
            hide-details
            placeholder="Default: <target>/no_video"
          >
            <template #append-inner>
              <v-tooltip location="top" max-width="300">
                <template #activator="{ props: tp }">
                  <v-icon v-bind="tp" size="small">mdi-help-circle-outline</v-icon>
                </template>
                Directory where metadata files with no corresponding video are moved to.
              </v-tooltip>
            </template>
          </v-text-field>
        </v-col>
      </v-row>
      <v-row dense class="mt-1">
        <v-col cols="12" md="4">
          <v-checkbox
            v-model="form.prefer_errors"
            label="Prefer fewer errors"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>

      <v-divider class="my-4" />

      <!-- Selection priorities -->
      <div class="text-subtitle-2 text-medium-emphasis mb-2">Selection priorities (top = highest)</div>
      <v-list density="compact" class="pa-0">
        <v-list-item
          v-for="(prio, idx) in form.selection_priorities"
          :key="prio"
          class="px-0"
        >
          <template #prepend>
            <span class="text-medium-emphasis mr-2" style="min-width: 20px">{{ idx + 1 }}.</span>
          </template>
          <v-list-item-title>{{ priorityLabels[prio] }}</v-list-item-title>
          <template #append>
            <v-btn
              icon="mdi-arrow-up"
              size="x-small"
              variant="text"
              :disabled="idx === 0"
              @click="movePriority(idx, -1)"
            />
            <v-btn
              icon="mdi-arrow-down"
              size="x-small"
              variant="text"
              :disabled="idx === form.selection_priorities.length - 1"
              @click="movePriority(idx, 1)"
            />
          </template>
        </v-list-item>
      </v-list>

      <v-divider class="my-4" />

      <!-- Semantic matching -->
      <div class="text-subtitle-2 text-medium-emphasis mb-2">Semantic matching</div>
      <v-row dense>
        <v-col cols="12" md="4">
          <v-checkbox
            v-model="form.remove_episode_nos"
            label="Remove episode numbers"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>
      <v-row dense class="mt-1">
        <v-col cols="12">
          <ListEditor
            v-model="form.semantic_prefixes"
            label="Semantic prefixes (regex patterns to strip)"
          />
        </v-col>
      </v-row>
    </v-card-text>
    <v-divider />
    <v-card-actions>
      <v-spacer />
      <v-btn
        color="primary"
        size="large"
        :disabled="!canSubmit"
        prepend-icon="mdi-play"
        @click="submit"
        class="text-none"
      >
        Start Scan
      </v-btn>
    </v-card-actions>
  </v-card>
</template>
