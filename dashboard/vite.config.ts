import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // the API runs next to Elasticsearch; in dev we proxy so the browser sees one origin
    proxy: { '/api': 'http://localhost:8000' },
  },
});
