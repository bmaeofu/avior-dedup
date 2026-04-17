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
      '/api/searchmove/ws': {
        target: 'http://127.0.0.1:8642',
        ws: true,
      },
      '/api/ws': {
        target: 'http://127.0.0.1:8642',
        ws: true,
      },
      '/api': {
        target: 'http://127.0.0.1:8642',
      },
    },
  },
})
