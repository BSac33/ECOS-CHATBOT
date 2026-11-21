import type { RouteRecordRaw } from 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** Titre de l'onglet (« … – ECOS – Entraînement ») */
    title?: string
    requiresAuth?: boolean
    /** Enseignants et administrateurs */
    requiresTeacher?: boolean
  }
}

// Chargement paresseux : chaque page est un morceau séparé du bundle
export const routes: RouteRecordRaw[] = [
  {
    path: '/', name: 'dashboard', component: () => import('./Dashboard.vue'),
    meta: { requiresAuth: true, title: 'Stations' },
  },
  {
    path: '/login', name: 'login', component: () => import('./components/LoginForm.vue'),
    meta: { title: 'Connexion' },
  },
  {
    path: '/compte', name: 'account', component: () => import('./AccountView.vue'),
    meta: { requiresAuth: true, title: 'Mon compte' },
  },
  {
    path: '/chat/:attemptId', name: 'chat', component: () => import('./ChatView.vue'), props: true,
    meta: { requiresAuth: true, title: 'Station en cours' },
  },
  {
    path: '/debrief/:attemptId', name: 'debrief', component: () => import('./Debrief.vue'), props: true,
    meta: { requiresAuth: true, title: 'Débriefing' },
  },
  // Atelier de création de stations (enseignants)
  {
    path: '/atelier', name: 'authoring', component: () => import('./authoring/AuthoringCases.vue'),
    meta: { requiresAuth: true, requiresTeacher: true, title: 'Atelier de stations' },
  },
  {
    path: '/atelier/tentatives/:attemptId', name: 'attempt-review', component: () => import('./authoring/AttemptReview.vue'),
    props: true, meta: { requiresAuth: true, requiresTeacher: true, title: 'Relecture d’une correction' },
  },
  {
    path: '/atelier/:caseId', name: 'case-editor', component: () => import('./authoring/CaseEditor.vue'), props: true,
    meta: { requiresAuth: true, requiresTeacher: true, title: 'Édition d’une station' },
  },
  {
    path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./NotFound.vue'),
    meta: { title: 'Page introuvable' },
  },
]
