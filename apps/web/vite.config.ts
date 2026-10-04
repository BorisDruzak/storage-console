import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/ready': 'http://127.0.0.1:8000', '/api': 'http://127.0.0.1:8000' } },
  test: {
    environment: 'jsdom',
    environmentOptions: { jsdom: { url: 'https://storage.example.test' } },
    setupFiles: ['./src/test-setup.ts'],
    coverage: { reporter: ['text', 'lcov'], include: ['src/**/*.{ts,tsx}'], exclude: ['src/*.test.*', 'src/main.tsx', 'src/test-setup.ts'] },
  },
});
