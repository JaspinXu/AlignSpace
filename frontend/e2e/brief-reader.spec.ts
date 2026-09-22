import { expect, test } from '@playwright/test';
import { designerJoins, goToPage, ownerCreatesProject, register, toAwaitingApproval, uploadAsset, write } from './flow';

test('both members read immutable brief versions without changing the project', async ({ browser }, testInfo) => {
  const ownerContext = await browser.newContext();
  const designerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  const designer = await designerContext.newPage();
  try {
    await register(owner, `reader-owner-${Date.now()}@example.com`);
    await register(designer, `reader-designer-${Date.now()}@example.com`);
    const code = await ownerCreatesProject(owner);
    await designerJoins(designer, code);
    for (let i = 0; i < 3; i++) await uploadAsset(owner, `reader-${i}.png`);
    await toAwaitingApproval(owner, designer);
    await owner.reload();
    await goToPage(owner, 'approval');
    await expect(owner.getByRole('button', { name: '查看设计说明书' })).toBeVisible();

    await owner.getByLabel('方案目标').fill('保留祖传书柜 · 第二版');
    owner.once('dialog', (dialog) => dialog.dismiss());
    await owner.getByRole('button', { name: '查看设计说明书' }).click();
    await expect(owner.getByLabel('方案目标')).toHaveValue('保留祖传书柜 · 第二版');
    // Save only through the existing workspace. It creates v2.
    await write(owner, '保存方案修改', '/briefs/1');
    await expect(owner.getByText('方案版本 v2', { exact: false })).toBeVisible();
    const beforeResponse = owner.waitForResponse((r) => r.url().endsWith('/state'));
    await owner.reload();
    const before = await (await beforeResponse).json();
    const writes: string[] = [];
    const captureWrites = (request: { url(): string; method(): string }) => {
      if (request.url().includes('/v1/projects') && request.method() !== 'GET') writes.push(request.url());
    };
    owner.on('request', captureWrites);
    designer.on('request', captureWrites);

    await owner.getByRole('button', { name: '查看设计说明书' }).click();
    await expect(owner.getByRole('heading', { name: '设计说明书', exact: true })).toBeVisible();
    await expect(owner.getByRole('region', { name: '设计目标' })).toContainText('保留祖传书柜');
    await expect(owner.getByRole('button', { name: '批准此版本' })).toHaveCount(0);
    await owner.getByLabel('说明书版本').selectOption('1');
    await expect(owner).toHaveURL(/version=1/);
    await expect(owner.getByRole('region', { name: '设计目标' })).not.toContainText('保留祖传书柜');
    await expect(owner.getByText(/历史审批记录不可用/)).toBeVisible();
    await owner.reload();
    await expect(owner.getByLabel('说明书版本')).toHaveValue('1');

    await designer.goto(owner.url());
    await expect(designer.getByRole('region', { name: '设计目标' })).not.toContainText('保留祖传书柜');
    await designer.getByLabel('说明书版本').selectOption('2');
    await expect(designer.getByRole('region', { name: '设计目标' })).toContainText('保留祖传书柜');
    await designer.goBack();
    await expect(designer.getByLabel('说明书版本')).toHaveValue('1');
    await designer.goForward();
    await expect(designer.getByLabel('说明书版本')).toHaveValue('2');

    await owner.setViewportSize({ width: 390, height: 844 });
    expect(await owner.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await owner.screenshot({ path: testInfo.outputPath('brief-reader-mobile.png'), fullPage: true });
    const afterResponse = owner.waitForResponse((r) => r.url().endsWith('/state'));
    await owner.getByRole('button', { name: '刷新状态' }).click();
    const after = await (await afterResponse).json();
    expect(after.projectState).toEqual(before.projectState);
    expect(writes).toEqual([]);
    await owner.getByRole('button', { name: '返回工作区' }).click();
    await expect(owner.getByRole('heading', { name: '方案审批' })).toBeVisible();
    await expect(owner).not.toHaveURL(/view=brief/);
    await owner.getByLabel('方案目标').fill('后退时保留的草稿');
    owner.once('dialog', (dialog) => dialog.dismiss());
    await owner.goBack();
    await expect(owner.getByLabel('方案目标')).toHaveValue('后退时保留的草稿');
    await expect(owner).not.toHaveURL(/view=brief/);
    owner.once('dialog', (dialog) => dialog.accept());
    await owner.goBack();
    await expect(owner.getByLabel('说明书版本')).toHaveValue('1');
    expect(writes).toEqual([]);
  } finally {
    await ownerContext.close();
    await designerContext.close();
  }
});
