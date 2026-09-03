import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // la API corre al lado de Elasticsearch; en desarrollo se hace proxy para que el navegador vea
    // un solo origen
    proxy: { '/api': 'http://localhost:8000' },
  },
});
