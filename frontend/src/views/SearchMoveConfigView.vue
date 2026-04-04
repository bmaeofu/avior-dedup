<script setup lang="ts">
import { ref } from 'vue'
import ConfigEditor from '../components/ConfigEditor.vue'
import TemplateEditor from '../components/TemplateEditor.vue'

const tab = ref('templates')
</script>

<template>
  <v-card>
    <v-tabs v-model="tab" color="primary">
      <v-tab value="templates" prepend-icon="mdi-file-document-multiple" class="text-none">
        Templates
      </v-tab>
      <v-tab value="paths" prepend-icon="mdi-folder-star" class="text-none">
        Path Suggestions
      </v-tab>
    </v-tabs>

    <v-card-text>
      <v-tabs-window v-model="tab">
        <v-tabs-window-item value="templates">
          <TemplateEditor />
        </v-tabs-window-item>
        <v-tabs-window-item value="paths">
          <ConfigEditor config-name="searchmove_paths" :columns="1" />
        </v-tabs-window-item>
      </v-tabs-window>
    </v-card-text>
  </v-card>
</template>
