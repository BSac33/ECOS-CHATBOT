// Chaque page se monte avec des réponses d'API simulées, sans avertissement de Vue
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import App from './App.vue'
import { createAppRouter } from './router'
import { fr } from './locale-fr'

const teacher = { id: 1, username: 'prof', full_name: 'Pr Martin', email: 'p@exemple.fr', is_active: true, role: 'teacher' }
const evaluation = {
  items: [{
    item_id: 'g1', criterion: 'Recherche le tabagisme', points_awarded: 1, points_possible: 2, is_validated: true,
    justification: 'Question posée.', citation: 'Vous fumez ?', citation_found: false, overridden: true,
  }],
  total_score: 1, total_possible: 2, percentage: 50, general_feedback: 'Bon entretien.',
  scales: [{ scale_id: 'ecouter', label: 'Aptitude à écouter', observable: true, level: 3, level_name: 'satisfaisante', justification: null }],
  global_performance: null, attitude_weight: 0.25, score_20: 11.5,
  reviewed_by: 'prof', reviewed_at: '2026-11-20T10:00:00', needs_review: true,
}
const station = { id: 1, title: 'Douleur thoracique', station_type: 'patient_interview', duration_seconds: 480,
  status: 'published', disciplines: ['Cardiologie'], edn_codes: [334], has_evaluation_grid: true }

const API: Record<string, unknown> = {
  '/api/api/users/me': teacher,
  '/api/api/cases': [station],
  '/api/api/cases/1': station,
  '/api/chat/attempts/a1/messages': [
    { id: 'm0', role: 'system', content: 'Consignes', created_at: '2026-11-20T10:00:00' },
    { id: 'm1', role: 'student', content: 'Bonjour', created_at: '2026-11-20T10:00:01', modality: 'text' },
    { id: 'm2', role: 'patient', content: 'Bonjour docteur', created_at: '2026-11-20T10:00:02', modality: 'voice',
      interrupted_by: 'voice', spoken_content: 'Bonjour…' },
  ],
  '/api/chat/attempts/a1/case-info': { case_id: 1, title: 'Douleur thoracique', station_type: 'patient_interview',
    duration_seconds: 480, is_test: false, interlocutor: 'patient', interlocutor_label: 'Patiente', domain: null },
  '/api/evaluation/attempts/a1/evaluate': { evaluation },
  '/api/evaluation/attempts/a1/transcript': { attempt_id: 'a1', case_id: 1, is_completed: true, transcript: [], interruptions: [] },
  '/api/evaluation/attempts/a1/review': { attempt_id: 'a1', case_id: 1, case_title: 'Douleur thoracique', username: 'etu1',
    full_name: null, completed_at: '2026-11-20T10:08:00', evaluation, transcript: [
      { id: 'm1', role: 'student', content: 'Bonjour', modality: 'text', interrupted_by: null, spoken_content: null, timestamp: null }] },
}

class FakeResizeObserver { observe() {} unobserve() {} disconnect() {} }

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

async function visit(path: string, { anonymous = false } = {}) {
  const warnings: string[] = []
  vi.spyOn(console, 'warn').mockImplementation((...args) => { warnings.push(String(args[0])) })
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input).split('?')[0]!
    if (url === '/api/api/users/me' && anonymous) return new Response('{"detail": "Non connecté"}', { status: 401 })
    if (url === '/api/chat/attempts/a1/time-remaining') {
      return new Response(JSON.stringify({ is_expired: false, seconds_remaining: 200,
        expires_at: new Date(Date.now() + 200_000).toISOString() }))
    }
    if (url in API) return new Response(JSON.stringify(API[url]))
    return new Response(JSON.stringify({ detail: 'Introuvable' }), { status: 404 })
  }))

  const pinia = createPinia()
  const router = createAppRouter(pinia, createMemoryHistory())
  await router.push(path)
  const wrapper = mount(App, {
    global: { plugins: [pinia, router, [PrimeVue, { theme: 'none', locale: fr }], ToastService] },
    attachTo: document.body,
  })
  await flushPromises()
  await new Promise((resolve) => setTimeout(resolve, 20))
  await flushPromises()
  const text = document.body.textContent ?? ''
  const route = router.currentRoute.value
  wrapper.unmount()
  return { text, warnings, route }
}

describe('pages', () => {
  it.each([
    ['/', 'Bienvenue, Pr Martin'],
    ['/compte', 'Exporter mes données'],
    ['/chat/a1', 'Patient simulé par une intelligence artificielle'],
    ['/debrief/a1', 'Correction relue par un enseignant le 20 novembre 2026'],
    ['/atelier/tentatives/a1', 'Relecture de la correction'],
    ['/adresse/inconnue', 'Page introuvable'],
  ])('%s', async (path, expected) => {
    const { text, warnings } = await visit(path)
    expect(text).toContain(expected)
    expect(warnings).toEqual([])
  })

  it('connexion : mention de transparence, sans comptes de démonstration', async () => {
    const { text, route } = await visit('/compte', { anonymous: true })
    expect(route.name).toBe('login')
    expect(route.query.redirect).toBe('/compte')
    expect(text).toContain("Cette plateforme utilise l'intelligence artificielle pour simuler les patients et proposer une correction.")
    expect(text).not.toContain('changeme')
  })

  it('débriefing : statut en texte, citation et mention de modification', async () => {
    const { text } = await visit('/debrief/a1')
    expect(text).toContain('Critère validé')
    expect(text).toContain('« Vous fumez ? »')
    expect(text).toContain("n'a pas été retrouvé mot pour mot")
    expect(text).toContain("modifié par l'enseignant")
  })
})
