import { defineConfig } from 'astro/config';
import svelte from '@astrojs/svelte';
import node from '@astrojs/node';

// Basado en copiaartcraft: CSS nativo scoped + tokens.css. Cero Tailwind.
//
// SSR (output: 'server' + adaptador Node) por decisión de integridad de datos:
// las páginas de resultados, fichas de fecha, ranking y perfiles se renderizan
// contra la API en cada request. Antes eran prerenderizadas y el `fetch` de
// build-time se tragaba el error (`try/catch` vacío), de modo que si el backend
// no estaba levantado durante `npm run build` las tablas se horneaban VACÍAS
// sin ningún aviso. Ver specs/03 §2.
export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  integrations: [svelte()],
  server: { port: 4321 },
});
