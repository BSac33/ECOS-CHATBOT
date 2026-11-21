# Frontend ECOS – Entraînement

Vue 3 + TypeScript (strict) + Vite + PrimeVue (locale française) + Pinia.

```bash
npm ci
npm run dev     # serveur de développement (port 5173, proxy vers l'API)
npm run build   # vue-tsc puis vite build
npm test        # Vitest (jsdom)
```

## Appels à l'API

- `src/services/http.ts` : client HTTP unique. Base `VITE_API_URL`, sinon `/api` (préfixe retiré par
  nginx en production et par le proxy de Vite en développement), cookie HttpOnly (`credentials: 'include'`),
  délai maximal (30 s, 240 s pour la correction et l'assistant de l'atelier), erreurs `ApiError` en français
  (le `detail` de l'API s'il est un texte), 401 : session vidée et retour à `/login?redirect=…`.
- `src/services/api.ts` (étudiants, compte, correction, relecture) et `src/authoring/api.ts` (atelier)
  décrivent les routes ; les types partagés sont dans `src/types.ts`.
- Appels directs, sans `/api` : flux SSE du chat (`src/services/chat.ts`, abandon après 60 s sans réponse),
  WebSocket du mode vocal (`src/services/voice.ts`) et documents (`/attachments/download/{id}`).

## Accessibilité (RGAA)

Interface en français, `lang="fr"`, titre de page par route, lien d'évitement, conversation en
`role="log"`, préfixes lus par les lecteurs d'écran (« Patient : », « Vous : », « Examinateur : »),
minuteur annoncé seulement aux paliers, `prefers-reduced-motion` respecté, contrastes ≥ 4,5:1.
La mention « Patient simulé par une intelligence artificielle » (AI Act, art. 50) figure dans l'en-tête
des stations et sur la page de connexion.
