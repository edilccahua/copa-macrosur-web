import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';

// Basado en copiaartcraft: CSS nativo scoped + tokens.css. Cero Tailwind.
export default defineConfig({
  integrations: [svelte()],
  server: { port: 4321 },
});
