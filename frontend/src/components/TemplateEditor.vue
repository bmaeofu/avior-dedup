<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useConfig } from '../composables/useConfig'
import ListEditor from './ListEditor.vue'

interface Template {
  name: string
  extensions: string[]
  search_expressions: string[]
}

const { data, loading, error, saved, load, save } = useConfig('searchmove_templates')
const templates = ref<Template[]>([])
const expandedPanels = ref<number[]>([])

onMounted(() => { load() })

watch(data, (val) => {
  if (val !== null) {
    templates.value = JSON.parse(JSON.stringify(val))
  }
})

function addTemplate() {
  templates.value.push({
    name: 'New template',
    extensions: ['.nfo'],
    search_expressions: [''],
  })
  expandedPanels.value = [templates.value.length - 1]
}

function removeTemplate(index: number) {
  templates.value.splice(index, 1)
}

function duplicateTemplate(index: number) {
  const copy = JSON.parse(JSON.stringify(templates.value[index]))
  copy.name = copy.name + ' (copy)'
  templates.value.splice(index + 1, 0, copy)
  expandedPanels.value = [index + 1]
}

function handleSave() {
  save(templates.value)
}
</script>

<template>
  <div>
    <v-progress-linear v-if="loading" indeterminate color="primary" />
    <v-alert v-if="error" type="error" density="compact" class="mb-3">{{ error }}</v-alert>

    <v-expansion-panels v-model="expandedPanels" variant="accordion">
      <v-expansion-panel
        v-for="(tmpl, i) in templates"
        :key="i"
      >
        <v-expansion-panel-title>
          <div class="d-flex align-center w-100">
            <span class="text-body-2">{{ tmpl.name || '(unnamed)' }}</span>
            <v-spacer />
            <v-chip size="x-small" variant="tonal" class="mr-2">
              {{ tmpl.extensions.join(', ') }}
            </v-chip>
            <v-chip size="x-small" variant="tonal">
              {{ tmpl.search_expressions.length }} expr
            </v-chip>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-row dense class="mb-3">
            <v-col cols="12" md="6">
              <v-text-field
                v-model="tmpl.name"
                label="Template name"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-combobox
                v-model="tmpl.extensions"
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
          </v-row>

          <ListEditor
            v-model="tmpl.search_expressions"
            label="Search expressions"
          />
          <div class="text-caption text-medium-emphasis mt-2">
            Examples: <code>sibling:.nfo:exists</code>, <code>sibling:.nfo:!exists</code>,
            <code>fileext:.mkv</code>, <code>rating:&gt;7&amp;genre:*Action*</code>
          </div>

          <div class="d-flex mt-3">
            <v-btn
              size="small"
              variant="tonal"
              prepend-icon="mdi-content-copy"
              class="text-none mr-2"
              @click="duplicateTemplate(i)"
            >
              Duplicate
            </v-btn>
            <v-btn
              size="small"
              variant="tonal"
              color="error"
              prepend-icon="mdi-delete"
              class="text-none"
              @click="removeTemplate(i)"
            >
              Remove
            </v-btn>
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <div class="d-flex align-center mt-4">
      <v-btn
        variant="tonal"
        prepend-icon="mdi-plus"
        class="text-none mr-4"
        @click="addTemplate"
      >
        Add Template
      </v-btn>
      <v-btn
        color="primary"
        :loading="loading"
        prepend-icon="mdi-content-save"
        class="text-none"
        @click="handleSave"
      >
        Save
      </v-btn>
      <v-fade-transition>
        <v-chip v-if="saved" color="success" size="small" class="ml-3">
          <v-icon start>mdi-check</v-icon> Saved
        </v-chip>
      </v-fade-transition>
    </div>
  </div>
</template>
