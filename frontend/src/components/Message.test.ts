import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import Message from './Message.vue'
import type { ChatMessage } from '../types'

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return { id: 'm1', role: 'patient', content: "J'ai mal à la poitrine.", created_at: '2026-11-20T10:15:00Z', ...overrides }
}

function render(msg: ChatMessage, props: Record<string, unknown> = {}) {
  return mount(Message, {
    props: { message: msg, ...props },
    global: { plugins: [[PrimeVue, { theme: 'none' }]] },
  })
}

describe('Message.vue', () => {
  it.each([
    ['patient', 'Patient : '],
    ['student', 'Vous : '],
    ['examiner', 'Examinateur : '],
    ['system', 'Information : '],
  ] as const)('préfixe masqué visuellement pour le rôle %s', (role, prefix) => {
    const wrapper = render(message({ role }))
    const hidden = wrapper.find('.message-content .sr-only')
    expect(hidden.exists()).toBe(true)
    expect(hidden.text()).toBe(prefix.trim())
    // Lu avant le contenu par les lecteurs d'écran
    expect(wrapper.find('.message-content').text().startsWith(prefix.trim())).toBe(true)
  })

  it("nomme l'interlocuteur simulé (professionnel de santé)", () => {
    const wrapper = render(message({ role: 'patient' }), { interlocutor: 'Cardiologue de garde' })
    expect(wrapper.find('.message-content .sr-only').text()).toBe('Cardiologue de garde :')
  })

  it("n'affiche la réplique coupée que jusqu'à la coupure", () => {
    const wrapper = render(message({ interrupted_by: 'voice', spoken_content: "J'ai mal…" }))
    expect(wrapper.find('.message-content').text()).toContain("J'ai mal…")
    expect(wrapper.text()).toContain('Coupé avant la fin')
  })

  it('message non envoyé : mention et bouton « Réessayer »', async () => {
    const msg = message({ role: 'student', content: 'Où avez-vous mal ?', failed: true })
    const wrapper = render(msg)
    expect(wrapper.text()).toContain('Non envoyé')
    const retry = wrapper.find('button')
    expect(retry.text()).toContain('Réessayer')
    await retry.trigger('click')
    expect(wrapper.emitted('retry')?.[0]).toEqual([msg])
  })

  it('lien de document vers le téléchargement direct', () => {
    const wrapper = render(message({ role: 'examiner', attachment_id: 'doc-1', attachment_mime_type: 'application/pdf' }))
    expect(wrapper.find('a.message-attachment-link').attributes('href')).toBe('/attachments/download/doc-1')
  })
})
