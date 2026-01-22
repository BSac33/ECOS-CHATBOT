import LoginForm from './components/LoginForm.vue';
import Dashboard from './Dashboard.vue';
import ChatView from './ChatView.vue';  

export const routes = [
    {'path': '/', 'name': 'dashboard', 'component': Dashboard, meta: { requiresAuth: true }},
    {'path': '/login', 'name': 'login', 'component': LoginForm},
    {'path': '/chat/:attemptId', 'name': 'chat', 'component': ChatView, props: true, meta: { requiresAuth: true }},
]