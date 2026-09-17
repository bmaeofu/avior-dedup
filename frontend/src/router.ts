import { createRouter, createWebHistory } from 'vue-router'
import JobView from './views/JobView.vue'
import ConfigView from './views/ConfigView.vue'
import SearchMoveView from './views/SearchMoveView.vue'
import SearchMoveConfigView from './views/SearchMoveConfigView.vue'
import HistoryView from './views/HistoryView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'job', component: JobView },
    { path: '/config', name: 'config', component: ConfigView },
    { path: '/history', name: 'history', component: HistoryView, props: { module: 'dedup' } },
    { path: '/searchmove', name: 'searchmove', component: SearchMoveView },
    { path: '/searchmove/config', name: 'searchmove-config', component: SearchMoveConfigView },
    { path: '/searchmove/history', name: 'searchmove-history', component: HistoryView, props: { module: 'searchmove' } },
  ],
})

export default router
