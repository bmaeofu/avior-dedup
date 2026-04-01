<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  modelValue: string[]
  label?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const newItem = ref('')

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
}
</script>

<template>
  <div>
    <v-label v-if="label" class="mb-2">{{ label }}</v-label>
    <div class="d-flex flex-wrap ga-2 mb-2">
      <v-chip
        v-for="(item, i) in modelValue"
        :key="i"
        closable
        @click:close="removeItem(i)"
      >
        {{ item }}
      </v-chip>
    </div>
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
</template>
