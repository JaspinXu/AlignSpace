import { useEffect, useRef, useState, type ReactNode } from 'react';

import { WORKSPACE_PAGES, type WorkspacePage } from '../navigation/workspaceRoute';

export const WORKSPACE_PAGE_LABELS: Record<WorkspacePage, string> = {
  overview: '项目概览',
  inspiration: '灵感与偏好',
  negotiation: '设计协商',
  space: '空间方案',
  approval: '方案审批',
};

type Props = {
  page: WorkspacePage;
  onNavigate: (page: WorkspacePage) => void;
  children: ReactNode;
  heading?: string;
  roleLabel?: string;
  actions?: ReactNode;
};

export function WorkspaceShell({ page, onNavigate, children, heading, roleLabel, actions }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMenuOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [menuOpen]);

  return (
    <div className="workspace-shell">
      <header className="workspace-topbar">
        <button
          ref={triggerRef}
          type="button"
          className="workspace-menu-toggle"
          aria-expanded={menuOpen}
          aria-controls="workspace-navigation"
          onClick={() => setMenuOpen((value) => !value)}
        >
          菜单
        </button>
        {heading && <h1 className="workspace-heading">{heading}</h1>}
        {roleLabel && <span className="workspace-role">{roleLabel}</span>}
        {actions && <div className="workspace-actions">{actions}</div>}
      </header>
      <div id="workspace-navigation" className={menuOpen ? 'workspace-menu is-open' : 'workspace-menu'}>
        <nav aria-label="工作区导航">
          <ul>
            {WORKSPACE_PAGES.map((item) => (
              <li key={item}>
                <button
                  type="button"
                  aria-current={page === item ? 'page' : undefined}
                  onClick={() => {
                    onNavigate(item);
                    setMenuOpen(false);
                  }}
                >
                  {WORKSPACE_PAGE_LABELS[item]}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </div>
      <main className="workspace-content">{children}</main>
    </div>
  );
}
