import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'

/**
 * Thème de l'application : bleu « clinique » sur fond ardoise.
 * Couleur principale en 600 (et non 500) : texte blanc sur bouton à un contraste ≥ 4,5:1.
 */
const scale = (name: string) =>
  Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map(n => [n, `{${name}.${n}}`]))

export const EcosTheme = definePreset(Aura, {
  semantic: {
    primary: scale('blue'),
    colorScheme: {
      light: {
        surface: { 0: '#ffffff', ...scale('slate') },
        primary: {
          color: '{primary.600}',
          contrastColor: '#ffffff',
          hoverColor: '{primary.700}',
          activeColor: '{primary.800}',
        },
        highlight: {
          background: '{primary.50}',
          focusBackground: '{primary.100}',
          color: '{primary.700}',
          focusColor: '{primary.800}',
        },
      },
    },
  },
})
