import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { PersistentPanel } from './PersistentPanel';

function Harness() {
  const [active, setActive] = useState(true);
  return (
    <>
      <button type="button" onClick={() => setActive((value) => !value)}>
        切换
      </button>
      <PersistentPanel active={active} id="inspiration">
        <input aria-label="偏好备注" defaultValue="" />
        <button type="button">面板内按钮</button>
      </PersistentPanel>
    </>
  );
}

describe('PersistentPanel', () => {
  it('keeps input value when the panel is hidden and shown again', async () => {
    render(<Harness />);
    await userEvent.type(screen.getByLabelText('偏好备注'), '保留我');
    await userEvent.click(screen.getByRole('button', { name: '切换' }));
    await userEvent.click(screen.getByRole('button', { name: '切换' }));
    expect(screen.getByLabelText('偏好备注')).toHaveValue('保留我');
  });

  it('removes hidden content from the accessibility tree', async () => {
    render(<Harness />);
    expect(screen.getByRole('button', { name: '面板内按钮' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '切换' }));
    expect(screen.queryByRole('button', { name: '面板内按钮' })).toBeNull();
    expect(screen.getByLabelText('偏好备注')).not.toBeVisible();
  });
});
