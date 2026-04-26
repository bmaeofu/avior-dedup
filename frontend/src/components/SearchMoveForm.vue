<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { SearchMoveRequest } from '../types'

const emit = defineEmits<{ start: [req: SearchMoveRequest] }>()

interface Template {
  name: string
  extensions: string[]
  search_expressions: string[]
}

const sourceSuggestions = ref<string[]>([])
const destSuggestions = ref<string[]>([])
const ignoredDirSuggestions = ref<string[]>([])
const templates = ref<Template[]>([])
const selectedTemplate = ref<string | null>(null)

async function sleep(ms: number): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, ms))
}

async function fetchWithRetry(url: string, retries = 6, delayMs = 500): Promise<Response | null> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const resp = await fetch(url)
      if (resp.ok) return resp
      if (resp.status >= 400 && resp.status < 500) return resp
    } catch {
      // Backend may still be starting up; retry shortly.
    }

    if (attempt < retries) {
      await sleep(delayMs)
    }
  }
  return null
}

onMounted(async () => {
  const [pathsRes, templatesRes, ignoredRes] = await Promise.all([
    fetchWithRetry('/api/config/searchmove_paths'),
    fetchWithRetry('/api/config/searchmove_templates'),
    fetchWithRetry('/api/config/searchmove_ignored_dirs'),
  ])

  if (pathsRes?.ok) {
    const data = await pathsRes.json()
    sourceSuggestions.value = data.source_paths ?? []
    destSuggestions.value = data.dest_paths ?? []
  }

  if (ignoredRes?.ok) {
    const ignoredFromConfig = await ignoredRes.json()
    ignoredDirSuggestions.value = Array.isArray(ignoredFromConfig) ? ignoredFromConfig : []
  }

  if (templatesRes?.ok) {
    templates.value = await templatesRes.json()
  }
})

function applyTemplate(name: string | null) {
  if (!name) return
  const tmpl = templates.value.find(t => t.name === name)
  if (!tmpl) return
  extensions.value = [...tmpl.extensions]
  expressionGroups.value = [...tmpl.search_expressions]
  rawMode.value = false
}

const mode = ref<'copy' | 'move' | 'delete' | 'test'>('test')
const source = ref('')
const dest = ref('')
const extensions = ref(['.nfo'])
const ignoredDirectories = ref<string[]>([])
const recursive = ref(false)
const logname = ref('searchmove_log.txt')

// Search expression builder
const rawMode = ref(false)
const rawExpressions = ref('')
const expressionGroups = ref<string[]>([''])

function addExpression() {
  expressionGroups.value.push('')
}

function removeExpression(index: number) {
  expressionGroups.value.splice(index, 1)
  if (expressionGroups.value.length === 0) {
    expressionGroups.value.push('')
  }
}

function buildExpressions(): string[] {
  if (rawMode.value) {
    return rawExpressions.value
      .split('\n')
      .map(s => s.trim())
      .filter(s => s.length > 0)
  }
  return expressionGroups.value.filter(s => s.trim().length > 0)
}

function submit() {
  const expressions = buildExpressions()
  if (!source.value || !dest.value || expressions.length === 0) return

  emit('start', {
    mode: mode.value,
    source: source.value,
    dest: dest.value,
    ignored_directories: ignoredDirectories.value,
    extensions: extensions.value,
    search_expressions: expressions,
    recursive: recursive.value,
    logname: logname.value,
  })
}
</script>

<template>
  <v-card>
    <v-card-item>
      <v-card-title class="text-none">Search & Move</v-card-title>
    </v-card-item>
    <v-divider />
    <v-card-text>
      <!-- Directories -->
      <div class="text-subtitle-2 text-medium-emphasis mb-2">Directories</div>
      <v-row dense>
        <v-col cols="12" md="6">
          <v-combobox
            v-model="source"
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
            v-model="dest"
            :items="destSuggestions"
            label="Destination"
            density="compact"
            variant="outlined"
            prepend-inner-icon="mdi-folder-move"
            hide-details
          />
        </v-col>
        <v-col cols="12">
          <v-combobox
            v-model="ignoredDirectories"
            :items="ignoredDirSuggestions"
            label="Ignored directories (optional)"
            density="compact"
            variant="outlined"
            prepend-inner-icon="mdi-folder-remove"
            hide-details
            multiple
            chips
            closable-chips
            clearable
          />
        </v-col>
      </v-row>

      <v-divider class="my-4" />

      <!-- Scan settings -->
      <div class="text-subtitle-2 text-medium-emphasis mb-2">Settings</div>
      <v-row dense align="center">
        <v-col cols="12" md="4">
          <v-btn-toggle v-model="mode" mandatory color="primary" density="compact">
            <v-btn value="test" class="text-none">Test</v-btn>
            <v-btn value="move" class="text-none">Move</v-btn>
            <v-btn value="copy" class="text-none">Copy</v-btn>
            <v-btn value="delete" class="text-none">Delete</v-btn>
          </v-btn-toggle>
        </v-col>
        <v-col cols="12" md="4">
          <v-combobox
            v-model="extensions"
            label="Extensions"
            density="compact"
            variant="outlined"
            hide-details
            multiple
            chips
            closable-chips
            :items="['.nfo', '.mkv', '.txt', '.log']"
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="logname"
            label="Log filename"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-col>
      </v-row>
      <v-row dense class="mt-1">
        <v-col cols="12" md="4">
          <v-checkbox
            v-model="recursive"
            label="Recursive search"
            density="compact"
            hide-details
          />
        </v-col>
      </v-row>

      <v-divider class="my-4" />

      <!-- Search expressions -->
      <div class="d-flex align-center mb-2">
        <div class="text-subtitle-2 text-medium-emphasis">Search Expressions</div>
        <v-select
          v-if="templates.length > 0"
          v-model="selectedTemplate"
          :items="templates.map(t => t.name)"
          label="Template"
          density="compact"
          variant="outlined"
          hide-details
          clearable
          class="ml-4"
          style="max-width: 300px;"
          @update:model-value="applyTemplate"
        />
        <v-spacer />
        <v-btn
          :prepend-icon="rawMode ? 'mdi-format-list-bulleted' : 'mdi-code-tags'"
          size="x-small"
          variant="tonal"
          @click="rawMode = !rawMode"
          class="text-none"
        >
          {{ rawMode ? 'List' : 'Raw' }}
        </v-btn>
      </div>

      <template v-if="rawMode">
        <v-textarea
          v-model="rawExpressions"
          label="One expression per line (& = AND, | = OR)"
          density="compact"
          variant="outlined"
          rows="3"
          hide-details
          placeholder="sibling:.nfo:exists&fileext:.mkv&#10;rating:>5.4&nfostatus:!exists"
        />
      </template>
      <template v-else>
        <v-row v-for="(_expr, i) in expressionGroups" :key="i" dense class="mb-1">
          <v-col>
            <v-text-field
              v-model="expressionGroups[i]"
              :label="`Expression ${i + 1}`"
              density="compact"
              variant="outlined"
              hide-details
              placeholder="sibling:.nfo:exists&fileext:.mkv"
            >
              <template #append-inner>
                <v-btn
                  icon="mdi-close"
                  size="x-small"
                  variant="text"
                  density="compact"
                  @click="removeExpression(i)"
                />
              </template>
            </v-text-field>
          </v-col>
        </v-row>
        <v-btn
          prepend-icon="mdi-plus"
          size="small"
          variant="tonal"
          class="text-none mt-1"
          @click="addExpression"
        >
          Add Expression
        </v-btn>
      </template>

      <div class="text-caption text-medium-emphasis mt-2">
        Use <code>&amp;</code> for AND, <code>|</code> for OR.
        XML tags: <code>tag:value</code>, wildcards: <code>tag:*val*</code>,
        existence: <code>tag:exists</code> / <code>tag:!exists</code>,
        numeric: <code>rating:&gt;7</code>, range: <code>rating:4-6</code>,
        metadata: <code>sibling:.nfo:exists</code> / <code>sibling:.nfo:!exists</code>,
        <code>fileext:.mkv</code>
      </div>
    </v-card-text>
    <v-divider />
    <v-card-actions>
      <v-spacer />
      <v-btn
        color="primary"
        size="large"
        :disabled="!source || !dest || buildExpressions().length === 0"
        prepend-icon="mdi-play"
        class="text-none"
        @click="submit"
      >
        Start Search
      </v-btn>
    </v-card-actions>
  </v-card>
</template>
