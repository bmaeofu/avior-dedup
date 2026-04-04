import { createRouter, createWebHistory } from 'vue-router'
import JobView from './views/JobView.vue'
import ConfigView from './views/ConfigView.vue'
import SearchMoveView from './views/SearchMoveView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'job', component: JobView },
    { path: '/config', name: 'config', component: ConfigView },
    { path: '/searchmove', name: 'searchmove', component: SearchMoveView },
  ],
})

export default router
