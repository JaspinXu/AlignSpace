export type WorkspacePage = 'overview' | 'inspiration' | 'negotiation' | 'space' | 'approval';

export const WORKSPACE_PAGES: readonly WorkspacePage[] = [
  'overview',
  'inspiration',
  'negotiation',
  'space',
  'approval',
] as const;

export function isWorkspacePage(value: string | null): value is WorkspacePage {
  return value !== null && (WORKSPACE_PAGES as readonly string[]).includes(value);
}

/**
 * Resolve the active workspace page from a URL. The legacy brief address
 * (`?view=brief&version=...`) belongs to the approval page so that returning
 * from the reader lands back on approval.
 */
export function parseWorkspacePage(url: URL): WorkspacePage {
  const requested = url.searchParams.get('page');
  if (isWorkspacePage(requested)) return requested;
  if (url.searchParams.get('view') === 'brief') return 'approval';
  return 'overview';
}

/** Build the URL for a page, keeping the project and dropping the legacy reader params. */
export function workspacePageUrl(url: URL, page: WorkspacePage): string {
  const next = new URL(url.href);
  next.searchParams.set('page', page);
  next.searchParams.delete('view');
  next.searchParams.delete('version');
  return next.href;
}
