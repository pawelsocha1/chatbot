import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/ask': 'http://localhost:8000',
      '/default-model.ifc': 'http://localhost:8000'
    }
  }
});
