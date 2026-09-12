import { defineConfig } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

// Each run gets isolated databases and a secret that is never logged or saved.
const dataDir = process.env.ALIGNSPACE_E2E_DATA_DIR || mkdtempSync(join(tmpdir(), 'alignspace-e2e-'));
process.env.ALIGNSPACE_E2E_DATA_DIR = dataDir;
const frontendUrl = 'http://127.0.0.1:5174';
const backendUrl = 'http://127.0.0.1:8013';

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: 0,
  use: {
    baseURL: frontendUrl,
    browserName: 'chromium',
    viewport: { width: 1280, height: 900 },
    screenshot: 'only-on-failure',
    // Traces can contain auth requests; keep them off for account flows.
    trace: 'off',
  },
  webServer: [
    {
      command: '../.venv/bin/uvicorn alignspace.main:app --host 127.0.0.1 --port 8013',
      url: `${backendUrl}/openapi.json`,
      reuseExistingServer: false,
      env: {
        ALIGNSPACE_AUTH_SECRET: randomBytes(32).toString('hex'),
        ALIGNSPACE_DEV: '1',
        ALIGNSPACE_ORIGINS: frontendUrl,
        ALIGNSPACE_DATABASE_URL: `sqlite:///${join(dataDir, 'accounts.db')}`,
        ALIGNSPACE_CHECKPOINT_PATH: join(dataDir, 'checkpoints.db'),
        ALIGNSPACE_ASSET_DIR: join(dataDir, 'assets'),
      },
    },
    {
      command: 'npm run dev -- --port 5174',
      url: frontendUrl,
      reuseExistingServer: false,
      env: { API_PROXY_TARGET: backendUrl },
    },
  ],
});
