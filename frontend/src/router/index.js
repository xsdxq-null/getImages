import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'task-list',
    component: () => import('../views/TaskListView.vue'),
    meta: { title: '任务列表' }
  },
  {
    path: '/tasks/create',
    name: 'task-create',
    component: () => import('../views/CreateTaskView.vue'),
    meta: { title: '创建任务' }
  },
  {
    path: '/tasks/:id(\\d+)',
    name: 'task-detail',
    component: () => import('../views/TaskDetailView.vue'),
    meta: { title: '任务详情' }
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  // Hash 模式，便于 FastAPI 静态托管
  history: createWebHashHistory(),
  routes
})

router.afterEach((to) => {
  document.title = to.meta?.title
    ? `${to.meta.title} · 阿里国际站素材抓取`
    : '阿里国际站素材抓取'
})

export default router
