import { expect, test } from '@playwright/test';
import { ownerCreatesProject, register, uploadAsset } from './flow';

test('a confirmed floor preference is bound, applied and survives a reload', async ({ browser }) => {
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  try {
    await register(owner, `binding-owner-${Date.now()}@example.com`);
    await ownerCreatesProject(owner);

    // Build a one-room draft first so a binding has a target.
    const space = owner.getByRole('region', { name: '空间草稿' });
    const created = owner.waitForResponse(
      (response) => response.url().endsWith('/space/rooms') && response.request().method() === 'POST',
    );
    await space.getByLabel('房间名称').fill('客厅');
    await space.getByRole('button', { name: '添加房间' }).click();
    expect((await created).status()).toBe(200);
    await expect(space.getByLabel('房间 客厅')).toBeVisible();

    // Turn a reference image into a confirmed floor "laying" preference. The
    // value is overridden to an exactly supported material option.
    for (let index = 0; index < 3; index++) {
      await uploadAsset(owner, `binding-${index}.png`);
    }
    const board = owner.getByRole('region', { name: '图片偏好候选' });
    await board.getByLabel('选择图片 binding-0.png').check();
    await board.getByLabel('喜欢这张图的哪些部分').fill('喜欢地板的铺设方式');
    await board.getByRole('button', { name: '生成候选偏好' }).click();
    await board.getByLabel('自定义取值 铺设方式').fill('herringbone');
    await board.getByRole('button', { name: '确认铺设方式候选' }).click();
    await expect(board.getByText(/已确认：herringbone/)).toBeVisible();

    // Reload so the workspace sees the new confirmed preference and version.
    await owner.reload();
    const shared = owner.getByRole('region', { name: '空间草稿' });
    await expect(shared.getByLabel('已确认地板偏好')).toBeVisible();
    await expect(shared.getByText('联合审批（说明书 + 空间）')).toBeVisible();

    await shared.getByLabel('已确认地板偏好').selectOption({ index: 1 });
    // The 3D preview cannot render herringbone; acknowledge before binding.
    await shared.getByLabel(/我理解 3D 预览不会呈现该铺法/).check();
    await shared.getByLabel('房间', { exact: true }).selectOption({ index: 1 });
    const bound = owner.waitForResponse(
      (response) => response.url().endsWith('/space/bindings') && response.request().method() === 'POST',
    );
    await shared.getByRole('button', { name: '绑定到房间' }).click();
    expect((await bound).status()).toBe(200);
    await expect(shared.getByText(/已绑定/)).toBeVisible();
    await expect(shared.getByText(/已绑定 · 完全匹配/)).toBeVisible();

    const applied = owner.waitForResponse(
      (response) => response.url().includes('/space/bindings/') && response.url().endsWith('/apply'),
    );
    await shared.getByRole('button', { name: '应用材质到空间' }).click();
    expect((await applied).status()).toBe(200);
    await expect(shared.getByText(/已应用到 v2/)).toBeVisible();

    // The applied material and binding survive a reload (backend authority).
    await owner.reload();
    const reloaded = owner.getByRole('region', { name: '空间草稿' });
    await expect(reloaded.getByText(/空间版本 v2/)).toBeVisible();
    await expect(reloaded.getByText(/已应用到 v2/)).toBeVisible();
  } finally {
    await ownerContext.close();
  }
});
