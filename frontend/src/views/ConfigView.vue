<script setup lang="ts">
import { ref } from 'vue'
import ConfigEditor from '../components/ConfigEditor.vue'

const tab = ref('ignored_files')

const tabs = [
  { value: 'ignored_files', title: 'Ignored Files', icon: 'mdi-file-hidden' },
  { value: 'ignored_dirs', title: 'Ignored Dirs', icon: 'mdi-folder-hidden' },
  { value: 'suffixes', title: 'Suffixes', icon: 'mdi-file-document-outline' },
  { value: 'episode_keywords', title: 'Episode Keywords', icon: 'mdi-tag-text' },
  { value: 'path_suggestions', title: 'Path Suggestions', icon: 'mdi-folder-star' },
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
          <ConfigEditor :config-name="t.value" />
        </v-tabs-window-item>
      </v-tabs-window>
    </v-card-text>
  </v-card>
</template>
