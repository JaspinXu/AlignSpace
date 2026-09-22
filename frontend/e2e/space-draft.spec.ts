import { expect, test } from '@playwright/test';
import { designerJoins, goToPage, ownerCreatesProject, register } from './flow';

test('a homeowner and designer share a persisted space draft; only the owner deletes', async ({
  browser,
}) => {
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  const designerContext = await browser.newContext();
  const designer = await designerContext.newPage();
  try {
    await register(owner, `space-owner-${Date.now()}@example.com`);
    const code = await ownerCreatesProject(owner);
    await goToPage(owner, 'space');

    const space = owner.getByRole('region', { name: '空间草稿' });
    await expect(space.getByText('尚无空间版本')).toBeVisible();
    await expect(space.getByRole('button', { name: '打开 3D 预览' })).toBeVisible();

    const created = owner.waitForResponse(
      (response) => response.url().endsWith('/space/rooms') && response.request().method() === 'POST',
    );
    await space.getByLabel('房间名称').fill('客厅');
    await space.getByRole('button', { name: '添加房间' }).click();
    expect((await created).status()).toBe(200);
    await expect(space.getByLabel('房间 客厅')).toBeVisible();
    await expect(space.getByText(/空间版本 v1/)).toBeVisible();

    // The authoritative backend plan survives a reload.
    await owner.reload();
    const reloaded = owner.getByRole('region', { name: '空间草稿' });
    await expect(reloaded.getByLabel('房间 客厅')).toBeVisible();

    // The designer shares edit access but cannot delete.
    await register(designer, `space-designer-${Date.now()}@example.com`);
    await designerJoins(designer, code);
    await goToPage(designer, 'space');
    const designerSpace = designer.getByRole('region', { name: '空间草稿' });
    await expect(designerSpace.getByLabel('房间 客厅')).toBeVisible();
    const shared = designer.waitForResponse(
      (response) => response.url().endsWith('/space/rooms') && response.request().method() === 'POST',
    );
    await designerSpace.getByLabel('房间名称').fill('书房');
    await designerSpace.getByRole('button', { name: '添加房间' }).click();
    expect((await shared).status()).toBe(200);
    await expect(designerSpace.getByLabel('房间 书房')).toBeVisible();
    await expect(designerSpace.getByRole('button', { name: '删除房间' })).toHaveCount(0);

    // Only the homeowner may delete; the deletion creates a new space version.
    owner.on('dialog', (dialog) => void dialog.accept());
    await owner.reload();
    const ownerSpace = owner.getByRole('region', { name: '空间草稿' });
    const deleted = owner.waitForResponse(
      (response) =>
        response.url().includes('/space/rooms/') && response.request().method() === 'DELETE',
    );
    await ownerSpace.getByRole('button', { name: '删除房间' }).last().click();
    expect((await deleted).status()).toBe(200);
    await expect(ownerSpace.getByLabel('房间 书房')).toHaveCount(0);
    await expect(ownerSpace.getByText(/空间版本 v3/)).toBeVisible();
  } finally {
    await ownerContext.close();
    await designerContext.close();
  }
});
