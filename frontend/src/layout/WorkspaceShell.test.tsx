import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { WORKSPACE_PAGES, type WorkspacePage } from '../navigation/workspaceRoute';
import { WorkspaceShell } from './WorkspaceShell';

function setup(page: WorkspacePage = 'overview') {
  const onNavigate = vi.fn();
  render(
    <WorkspaceShell page={page} onNavigate={onNavigate} heading="客厅" roleLabel="屋主">
      <p>页面内容</p>
    </WorkspaceShell>,
  );
  return { onNavigate };
}

describe('WorkspaceShell', () => {
  it('renders all five navigation entries', () => {
    setup();
    for (const page of WORKSPACE_PAGES) {
      expect(screen.getByRole('button', { name: pageLabel(page) })).toBeVisible();
    }
  });

  it('marks the current page with aria-current', () => {
    setup('space');
    expect(screen.getByRole('button', { name: '空间方案' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: '项目概览' })).not.toHaveAttribute('aria-current');
  });

  it('navigates to the chosen page', async () => {
    const { onNavigate } = setup();
    await userEvent.click(screen.getByRole('button', { name: '设计协商' }));
    expect(onNavigate).toHaveBeenCalledWith('negotiation');
  });

  it('closes the mobile menu on Escape and returns focus to the trigger', async () => {
    setup();
    const trigger = screen.getByRole('button', { name: '菜单' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveFocus();
  });
});

function pageLabel(page: WorkspacePage): string {
  return {
    overview: '项目概览',
    inspiration: '灵感与偏好',
    negotiation: '设计协商',
    space: '空间方案',
    approval: '方案审批',
  }[page];
}
