<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  modelValue: string[]
  label?: string
}>()

const labelMap: Record<string, string> = {
  series_keep_episode_nos: 'Series: Keep Episode Numbers',
  episode_keep_keywords: 'Episode Keep Keywords',
  episode_keep_keywords_years: 'Episode Keep Keywords (Years)',
  candidate_suffixes: 'Candidate Suffixes',
  video_suffixes: 'Video Suffixes',
  source_paths: 'Source Paths',
  target_paths: 'Target Paths',
}

const displayLabel = computed(() => {
  if (!props.label) return ''
  return labelMap[props.label] ?? props.label.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const newItem = ref('')
const editingIndex = ref<number | null>(null)
const editValue = ref('')

function addItem() {
  const val = newItem.value.trim()
  if (val && !props.modelValue.includes(val)) {
    emit('update:modelValue', [...props.modelValue, val])
  }
  newItem.value = ''
}

function removeItem(index: number) {
  const updated = [...props.modelValue]
  updated.splice(index, 1)
  emit('update:modelValue', updated)
  if (editingIndex.value === index) editingIndex.value = null
}

function startEdit(index: number) {
  editingIndex.value = index
  editValue.value = props.modelValue[index]
}

function commitEdit() {
  if (editingIndex.value === null) return
  const val = editValue.value.trim()
  if (val && val !== props.modelValue[editingIndex.value]) {
    const updated = [...props.modelValue]
    updated[editingIndex.value] = val
    emit('update:modelValue', updated)
  }
  editingIndex.value = null
}
</script>

<template>
  <v-card variant="flat" rounded="lg" class="list-editor-card">
    <template v-if="label">
      <v-card-item>
        <v-card-title class="text-none">{{ displayLabel }}</v-card-title>
      </v-card-item>
      <v-divider />
    </template>
    <v-list density="compact" class="py-0" bg-color="transparent">
      <v-list-item
        v-for="(item, i) in modelValue"
        :key="i"
        @dblclick="startEdit(i)"
      >
        <template v-if="editingIndex === i">
          <v-text-field
            v-model="editValue"
            density="compact"
            variant="plain"
            hide-details
            autofocus
            class="text-body-2"
            @keydown.enter.prevent="commitEdit"
            @keydown.esc.prevent="editingIndex = null"
            @blur="commitEdit"
          />
        </template>
        <v-list-item-title v-else class="text-body-2">{{ item }}</v-list-item-title>
        <template #append>
          <v-btn
            icon="mdi-close"
            size="x-small"
            variant="text"
            @click="removeItem(i)"
          />
        </template>
      </v-list-item>
      <v-list-item v-if="modelValue.length === 0">
        <v-list-item-title class="text-body-2 text-disabled">No items</v-list-item-title>
      </v-list-item>
    </v-list>
    <v-divider />
    <div class="pa-3">
      <v-text-field
        v-model="newItem"
        density="compact"
        variant="outlined"
        placeholder="Type and press Enter to add"
        hide-details
        @keydown.enter.prevent="addItem"
      >
        <template #append-inner>
          <v-btn
            icon="mdi-plus"
            size="small"
            variant="text"
            @click="addItem"
          />
        </template>
      </v-text-field>
    </div>
  </v-card>
</template>

<style scoped>
.list-editor-card {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
</style>
