import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import type { InlineConfig } from 'vitest/node';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { '/v1': { target: env.API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: false } },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
    } satisfies InlineConfig,
  };
});
