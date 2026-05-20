<script setup lang="ts">
import { ref } from 'vue'
import ConfigEditor from '../components/ConfigEditor.vue'

const tab = ref('ignored_files')

const tabs = [
  { value: 'ignored_files', title: 'Ignored Files', icon: 'mdi-file-hidden', columns: 2 },
  { value: 'ignored_dirs', title: 'Ignored Dirs', icon: 'mdi-folder-hidden', columns: 2 },
    { value: 'semantic_prefixes', title: 'Semantic Prefixes', icon: 'mdi-format-letter-case', columns: 1 },
  { value: 'suffixes', title: 'Suffixes', icon: 'mdi-file-document-outline', columns: 2 },
  { value: 'episode_keywords', title: 'Episode Keywords', icon: 'mdi-tag-text', columns: 2 },
  { value: 'path_suggestions', title: 'Path Suggestions', icon: 'mdi-folder-star', columns: 1 },
]
</script>

<template>
  <v-card>
    <v-tabs v-model="tab" color="primary">
      <v-tab
        v-for="t in tabs"
        :key="t.value"
        :value="t.value"
        :prepend-icon="t.icon"
        class="text-none"
      >
        {{ t.title }}
      </v-tab>
    </v-tabs>

    <v-card-text>
      <v-tabs-window v-model="tab">
        <v-tabs-window-item
          v-for="t in tabs"
          :key="t.value"
          :value="t.value"
        >
          <ConfigEditor :config-name="t.value" :columns="t.columns" />
        </v-tabs-window-item>
      </v-tabs-window>
    </v-card-text>
  </v-card>
</template>
