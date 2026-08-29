import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  root: 'client',
  server: {
    port: 5173,
    fs: {
      allow: ['..'],   // allow serving files from the project root (src/)
    },
    proxy: {
      '/socket.io': {
        target: 'http://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    rollupOptions: {
      // help.html is a second entry point; without listing it here Vite would
      // only build index.html and the Guide link would 404 in prod.
      input: {
        main: fileURLToPath(new URL('./client/index.html', import.meta.url)),
        help: fileURLToPath(new URL('./client/help.html', import.meta.url)),
      },
    },
  },
});
