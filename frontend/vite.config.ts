import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
  ],
  server: {
    proxy: {
      '/api/ws': {
        target: 'http://localhost:8642',
        ws: true,
      },
      '/api': {
        target: 'http://localhost:8642',
      },
    },
  },
})
