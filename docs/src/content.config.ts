import { defineCollection, z } from 'astro:content'
import { docsLoader } from '@astrojs/starlight/loaders'
import { docsSchema } from '@astrojs/starlight/schema'
import { glob } from 'astro/loaders'

// Collection Starlight standard : pages migrées dans src/content/docs/ (le
// contenu de l'ancien docs/ VitePress, sous src/content/docs/docs/ pour
// préserver les URL /docs/...).
const docs = defineCollection({
  loader: docsLoader(),
  schema: docsSchema(),
})

// README/RUNBOOK COLOCALISÉS avec le code, lus EN PLACE (source unique, ADR
// 0023/0089) : un glob les lit là où ils vivent (base: racine du dépôt), sans
// copie. Rendus par src/pages/[...slug].astro dans un <StarlightPage>. Le titre
// est dérivé du premier H1 (ces fichiers n'ont pas de frontmatter).
const colocated = defineCollection({
  loader: glob({
    base: '..',
    // Zones colocalisées (hors docs/, hors source vendoré gitignoré et exclus).
    pattern: [
      // .md de la racine SAUF README.md : il reste hors documentation (point
      // d'entrée GitHub du dépôt, jamais publié — déjà exclu en VitePress).
      '*.md',
      '!README.md',
      'apps/**/README.md',
      'bench/**/{README,RESULTS}.md',
      'bootstrap/**/{README,RUNBOOK,IMPLICATIONS,TODO}.md',
      'contract/README.md',
      'platform/**/README.md',
      'platform/hardware.md',
      'storage/**/{README,RUNBOOK}.md',
      // exclusions
      '!**/node_modules/**',
      '!CHANGELOG.md',
      '!**/CHANGELOG.md',
      '!LICENSE.md',
      '!apps/redcap/source/**',
      '!platform/redcap/image/source/**',
    ],
  }),
  schema: z.object({}).passthrough(),
})

export const collections = {
  docs,
  colocated,
}
