import { describe, expect, it } from 'vitest';

import { parseWorkspacePage, workspacePageUrl } from './workspaceRoute';

describe('parseWorkspacePage', () => {
  it('defaults to the overview page', () => {
    expect(parseWorkspacePage(new URL('http://localhost/?project=p'))).toBe('overview');
  });

  it('accepts each of the five pages', () => {
    for (const page of ['overview', 'inspiration', 'negotiation', 'space', 'approval'] as const) {
      expect(parseWorkspacePage(new URL(`http://localhost/?project=p&page=${page}`))).toBe(page);
    }
  });

  it('falls back to the overview page for an unknown page', () => {
    expect(parseWorkspacePage(new URL('http://localhost/?project=p&page=chat'))).toBe('overview');
    expect(parseWorkspacePage(new URL('http://localhost/?project=p&page='))).toBe('overview');
  });

  it('treats the legacy brief address as the approval page', () => {
    expect(parseWorkspacePage(new URL('http://localhost/?project=p&view=brief&version=2'))).toBe(
      'approval',
    );
  });
});

describe('workspacePageUrl', () => {
  it('keeps the project and sets the requested page', () => {
    const url = new URL('http://localhost/?project=p');
    const next = new URL(workspacePageUrl(url, 'space'));
    expect(next.searchParams.get('project')).toBe('p');
    expect(next.searchParams.get('page')).toBe('space');
  });

  it('drops the legacy brief view and version when navigating to a page', () => {
    const next = new URL(
      workspacePageUrl(new URL('http://localhost/?project=p&view=brief&version=2'), 'approval'),
    );
    expect(next.searchParams.has('view')).toBe(false);
    expect(next.searchParams.has('version')).toBe(false);
    expect(next.searchParams.get('page')).toBe('approval');
  });

  it('does not mutate the input URL', () => {
    const url = new URL('http://localhost/?project=p&view=brief&version=2');
    workspacePageUrl(url, 'space');
    expect(url.searchParams.get('view')).toBe('brief');
  });
});
