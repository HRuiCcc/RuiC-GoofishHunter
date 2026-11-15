import { createRouter, createWebHistory } from 'vue-router'
import OverviewView from './views/OverviewView.vue'
import WatchesView from './views/WatchesView.vue'
import ItemsView from './views/ItemsView.vue'
import RunsView from './views/RunsView.vue'
import SettingsView from './views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: OverviewView, meta: { title: '概览' } },
    { path: '/watches', name: 'watches', component: WatchesView, meta: { title: '关注' } },
    { path: '/items', name: 'items', component: ItemsView, meta: { title: '商品库' } },
    { path: '/runs', name: 'runs', component: RunsView, meta: { title: '运行' } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { title: '设置' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} · 闲鱼猎手` : '闲鱼猎手'
})

export default router
