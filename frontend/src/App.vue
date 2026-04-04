<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useTheme } from 'vuetify'

const gitHash = import.meta.env.VITE_GIT_HASH || 'dev'
const theme = useTheme()
const drawer = ref(true)
const rail = ref(true)

type ThemeMode = 'auto' | 'light' | 'dark'
const themeMode = ref<ThemeMode>((localStorage.getItem('themeMode') as ThemeMode) ?? 'auto')

const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

function applyTheme() {
  if (themeMode.value === 'auto') {
    theme.global.name.value = mediaQuery.matches ? 'dark' : 'light'
  } else {
    theme.global.name.value = themeMode.value
  }
}

function cycleTheme() {
  const modes: ThemeMode[] = ['auto', 'light', 'dark']
  const next = modes[(modes.indexOf(themeMode.value) + 1) % modes.length]
  themeMode.value = next
}

const themeIcon = ref('')
function updateIcon() {
  if (themeMode.value === 'auto') themeIcon.value = 'mdi-theme-light-dark'
  else if (themeMode.value === 'light') themeIcon.value = 'mdi-weather-sunny'
  else themeIcon.value = 'mdi-weather-night'
}

watch(themeMode, () => {
  localStorage.setItem('themeMode', themeMode.value)
  applyTheme()
  updateIcon()
})

mediaQuery.addEventListener('change', () => {
  if (themeMode.value === 'auto') applyTheme()
})

onMounted(() => {
  applyTheme()
  updateIcon()
})
</script>

<template>
  <v-app>
    <v-app-bar density="compact" elevation="2">
      <v-app-bar-nav-icon @click="rail = !rail" />
      <v-app-bar-title>Avior Dedup</v-app-bar-title>
      <v-spacer />
      <span class="text-caption text-medium-emphasis mr-2">{{ gitHash }}</span>
      <v-btn
        :icon="themeIcon"
        @click="cycleTheme"
      />
    </v-app-bar>

    <v-navigation-drawer v-model="drawer" :rail="rail">
      <v-list nav density="compact">
        <v-list-subheader v-show="!rail">Dedup</v-list-subheader>
        <v-list-item
          prepend-icon="mdi-magnify-scan"
          title="Scan"
          to="/"
        />
        <v-list-item
          prepend-icon="mdi-cog"
          title="Settings"
          to="/config"
        />

        <v-divider class="my-1" />

        <v-list-subheader v-show="!rail">Search & Move</v-list-subheader>
        <v-list-item
          prepend-icon="mdi-file-search"
          title="Search"
          to="/searchmove"
        />
      </v-list>
    </v-navigation-drawer>

    <v-main>
      <v-container fluid>
        <router-view />
      </v-container>
    </v-main>
  </v-app>
</template>

