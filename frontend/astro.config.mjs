import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';
import cloudflare from '@astrojs/cloudflare';

// Basado en copiaartcraft: CSS nativo scoped + tokens.css. Cero Tailwind.
// SSR en Cloudflare Pages con @astrojs/cloudflare para render dinámico en edge.
export default defineConfig({
  output: 'server',
  adapter: cloudflare({
    imageService: 'passthrough',
  }),
  integrations: [svelte()],
  server: { port: 4321 },
});
