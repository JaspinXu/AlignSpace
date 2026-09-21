import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

/**
 * Static regression guard for the OpenPlan3D bridge: our own space module must
 * never talk to an upstream cloud service, and must never put a credential in
 * a URL. The upstream tree itself is hardened by scripts/fetch_openplan3d.sh.
 */
const sources = ['./spaceAdapter.ts', './SpaceBoard.tsx'];

function read(name: string): string {
  return readFileSync(new URL(name, import.meta.url), 'utf8');
}

describe('space module has no upstream cloud dependency', () => {
  it.each(sources)('%s contains no analytics, share or Firebase endpoints', (name) => {
    const text = read(name).toLowerCase();
    for (const forbidden of [
      'google-analytics',
      'googletagmanager',
      'firebase',
      'firebasestorage',
      'openplan3d.firebaseapp',
    ]) {
      expect(text).not.toContain(forbidden);
    }
  });

  it.each(sources)('%s only references local http(s) origins', (name) => {
    const text = read(name);
    const urls = text.match(/https?:\/\/[^\s"'`)]+/g) ?? [];
    for (const url of urls) {
      expect(url).toMatch(/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?(\/|$)/);
    }
  });

  it.each(sources)('%s never embeds a token in a URL', (name) => {
    const text = read(name).toLowerCase();
    expect(text).not.toMatch(/[?&](token|access_token|authorization)=/);
    expect(text).not.toContain('accesstoken=');
  });
});
