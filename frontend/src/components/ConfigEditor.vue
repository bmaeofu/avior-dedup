<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue'
import { useConfig } from '../composables/useConfig'
import ChipListEditor from './ChipListEditor.vue'

const props = defineProps<{
  configName: string
}>()

const { data, loading, error, saved, load, save } = useConfig(props.configName)
const localData = ref<any>(null)

onMounted(() => {
  load()
})

watch(data, (val) => {
  if (val !== null) {
    localData.value = JSON.parse(JSON.stringify(val))
  }
})

const isDict = computed(() =>
  localData.value !== null && typeof localData.value === 'object' && !Array.isArray(localData.value)
)

const isList = computed(() => Array.isArray(localData.value))

function updateList(newVal: string[]) {
  localData.value = newVal
}

function updateDictKey(key: string, newVal: string[]) {
  localData.value[key] = newVal
}

function handleSave() {
  save(localData.value)
}
</script>

<template>
  <div>
    <v-progress-linear v-if="loading" indeterminate color="primary" />

    <v-alert v-if="error" type="error" density="compact" class="mb-3">{{ error }}</v-alert>

    <template v-if="localData !== null && isList">
      <ChipListEditor :model-value="localData" @update:model-value="updateList" />
    </template>

    <template v-else-if="localData !== null && isDict">
      <div v-for="(value, key) in localData" :key="key" class="mb-4">
        <ChipListEditor
          v-if="Array.isArray(value)"
          :model-value="localData[key]"
          @update:model-value="(v: string[]) => updateDictKey(String(key), v)"
          :label="String(key)"
        />
        <v-text-field
          v-else
          v-model="localData[key]"
          :label="String(key)"
          density="compact"
          variant="outlined"
        />
      </div>
    </template>

    <div class="d-flex align-center mt-4">
      <v-btn color="primary" :loading="loading" prepend-icon="mdi-content-save" @click="handleSave">
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
