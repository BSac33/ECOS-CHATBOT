import LoginForm from './components/LoginForm.vue';
import Dashboard from './Dashboard.vue';
import ChatView from './ChatView.vue';
import Debrief from './Debrief.vue';

export const routes = [
    {'path': '/', 'name': 'dashboard', 'component': Dashboard, meta: { requiresAuth: true }},
    {'path': '/login', 'name': 'login', 'component': LoginForm},
    {'path': '/chat/:attemptId', 'name': 'chat', 'component': ChatView, props: true, meta: { requiresAuth: true }},
    {'path': '/debrief/:attemptId', 'name': 'debrief', 'component': Debrief, props: true, meta: { requiresAuth: true }},
    // Route temporaire pour l'évaluation (à implémenter)
    {'path': '/evaluation/:attemptId', 'name': 'evaluation', component: () => import('./components/EvaluationPlaceholder.vue'), props: true, meta: { requiresAuth: true }},
]