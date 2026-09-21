import { expect, test } from '@playwright/test';
import {
  designerAddConstraint,
  designerJoins,
  ownerCreatesProject,
  register,
  toAwaitingApproval,
  uploadAsset,
} from './flow';

test('two accounts jointly approve a brief+space plan and it expires after a brief change', async ({
  browser,
}) => {
  const ownerContext = await browser.newContext();
  const designerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  const designer = await designerContext.newPage();
  try {
    await register(owner, `joint-owner-${Date.now()}@example.com`);
    await register(designer, `joint-designer-${Date.now()}@example.com`);
    const code = await ownerCreatesProject(owner);
    await designerJoins(designer, code);
    for (let index = 0; index < 3; index++) {
      await uploadAsset(owner, `joint-${index}.png`);
    }
    await toAwaitingApproval(owner, designer);

    // A space version must exist before a joint approval is meaningful.
    await owner.reload();
    const space = owner.getByRole('region', { name: '空间草稿' });
    const created = owner.waitForResponse(
      (response) => response.url().endsWith('/space/rooms') && response.request().method() === 'POST',
    );
    await space.getByLabel('房间名称').fill('客厅');
    await space.getByRole('button', { name: '添加房间' }).click();
    expect((await created).status()).toBe(200);
    await expect(space.getByText(/空间版本 v1/)).toBeVisible();
    await expect(space.getByText('尚未双方批准')).toBeVisible();

    const ownerApproved = owner.waitForResponse(
      (response) => response.url().endsWith('/space/approvals') && response.request().method() === 'POST',
    );
    await space.getByRole('button', { name: '联合批准当前方案' }).click();
    expect((await ownerApproved).status()).toBe(200);
    await expect(space.getByText('尚未双方批准')).toBeVisible();

    // The designer approves the exact same brief and space versions.
    await designer.reload();
    const designerSpace = designer.getByRole('region', { name: '空间草稿' });
    await expect(designerSpace.getByText('尚未双方批准')).toBeVisible();
    const designerApproved = designer.waitForResponse(
      (response) => response.url().endsWith('/space/approvals') && response.request().method() === 'POST',
    );
    await designerSpace.getByRole('button', { name: '联合批准当前方案' }).click();
    expect((await designerApproved).status()).toBe(200);
    await expect(designerSpace.getByText('双方已批准')).toBeVisible();

    // A later brief change (designer constraint) expires the joint approval but
    // keeps the historical approvals visible.
    await designerAddConstraint(designer, '追加的预算约束');
    await owner.reload();
    const after = owner.getByRole('region', { name: '空间草稿' });
    await expect(after.getByText('尚未双方批准')).toBeVisible();
    await expect(after.getByText(/已记录批准：屋主、设计师/)).toBeVisible();
  } finally {
    await ownerContext.close();
    await designerContext.close();
  }
});
