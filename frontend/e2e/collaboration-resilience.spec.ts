import { expect, test, type Browser, type Page } from '@playwright/test';
import {
  designerAddConstraint,
  designerJoins,
  ownerCreatesProject,
  register,
  toAwaitingApproval,
  toDesignerWait,
  uploadAsset,
  write,
} from './flow';

const BASE = 'http://127.0.0.1:5174';

async function bootstrap(browser: Browser) {
  const ownerContext = await browser.newContext({ baseURL: BASE });
  const designerContext = await browser.newContext({ baseURL: BASE });
  const owner = await ownerContext.newPage();
  const designer = await designerContext.newPage();
  await register(owner, `owner-${Date.now()}@example.com`);
  await register(designer, `designer-${Date.now()}@example.com`);
  const code = await ownerCreatesProject(owner);
  await designerJoins(designer, code);
  for (let index = 0; index < 3; index++) await uploadAsset(owner, `room-${index}.png`);
  return { ownerContext, designerContext, owner, designer };
}

async function submitConstraint(page: Page, statement: string): Promise<Response> {
  await page.getByLabel('约束内容').fill(statement);
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/constraints') && r.request().method() !== 'GET',
  );
  await page.getByRole('button', { name: '保存约束', exact: true }).click();
  return response;
}

async function updateConstraint(
  page: Page,
  editLabel: string,
  statement: string,
): Promise<Response> {
  await page.getByRole('button', { name: `编辑 ${editLabel}`, exact: true }).click();
  await page.getByLabel('约束内容').fill(statement);
  const response = page.waitForResponse(
    (r) => r.url().includes('/constraints/') && r.request().method() === 'PATCH',
  );
  await page.getByRole('button', { name: '更新约束', exact: true }).click();
  return response;
}

test('concurrent constraint edits keep the stale tab input and allow a resubmit', async ({
  browser,
}) => {
  const { designerContext, owner, designer } = await bootstrap(browser);
  await toDesignerWait(owner);
  const tabA = designer;
  await tabA.reload();
  const tabB = await designerContext.newPage();
  await tabB.goto(tabA.url());
  await expect(tabB.getByRole('heading', { name: '当前任务' })).toBeVisible();

  const first = await submitConstraint(tabA, 'A 约束');
  expect((await first).status()).toBe(200);

  const conflicting = await submitConstraint(tabB, 'B 约束');
  expect((await conflicting).status()).toBe(409);
  await expect(tabB.getByText(/输入已保留/)).toBeVisible();
  await expect(tabB.getByLabel('约束内容')).toHaveValue('B 约束');

  await expect(tabB.locator('.sidebar')).toContainText('A 约束');
  const retried = await submitConstraint(tabB, 'B 约束');
  expect((await retried).status()).toBe(200);
  await expect(tabB.locator('.sidebar')).toContainText('B 约束');
});

test('a stale tab cannot write its old answer into the next question', async ({ browser }) => {
  const { ownerContext, owner } = await bootstrap(browser);
  await write(owner, '启动分析', '/analysis-runs', 202);
  const tabA = owner;
  const tabB = await ownerContext.newPage();
  await tabB.goto(tabA.url());
  await expect(tabB.getByRole('heading', { name: '当前任务' })).toBeVisible();

  const partsA = tabA.getByRole('checkbox');
  for (let index = 0; index < (await partsA.count()); index++) await partsA.nth(index).check();
  await write(tabA, '提交回答', '/answer', 202);
  await expect(tabA.getByRole('button', { name: '喜欢', exact: true }).first()).toBeVisible();

  const partsB = tabB.getByRole('checkbox');
  for (let index = 0; index < (await partsB.count()); index++) await partsB.nth(index).check();
  const stale = tabB.waitForResponse(
    (r) => r.url().endsWith('/answer') && r.request().method() !== 'GET',
  );
  await tabB.getByRole('button', { name: '提交回答', exact: true }).click();
  expect((await stale).status()).toBe(404);
  await expect(tabB.getByRole('checkbox').first()).toBeChecked();

  await tabB.reload();
  await expect(tabB.getByRole('button', { name: '喜欢', exact: true }).first()).toBeVisible();
});

test('an approval is rejected after another tab changes a constraint, then regenerated', async ({
  browser,
}) => {
  const { owner, designer } = await bootstrap(browser);
  await toAwaitingApproval(owner, designer);
  await owner.reload();
  await expect(owner.getByRole('button', { name: '批准此版本' })).toBeVisible();

  // Freeze the owner's view so it still holds the pre-change brief.
  await owner.route('**/state', (route) => route.abort());
  await designer.reload();
  await designerAddConstraint(designer, '追加的预算约束');
  await expect(designer.getByText('方案已过时，请重新生成后再审批。')).toBeVisible();

  const rejected = owner.waitForResponse(
    (r) => r.url().endsWith('/approvals') && r.request().method() !== 'GET',
  );
  await owner.getByRole('button', { name: '批准此版本' }).click();
  expect((await rejected).status()).toBe(409);
  await owner.unroute('**/state');
  await expect(owner.getByText(/输入已保留/)).toBeVisible();

  await owner.reload();
  await expect(owner.getByText('方案已过时，请重新生成后再审批。')).toBeVisible();
  await write(owner, '重新生成方案', '/realign', 200);
  await expect(owner.getByText('方案版本 v2', { exact: false })).toBeVisible();
  await write(owner, '批准此版本', '/approvals');

  await designer.reload();
  await expect(designer.getByText('方案版本 v2', { exact: false })).toBeVisible();
  await write(designer, '批准此版本', '/approvals');
  await expect(designer.locator('.meta')).toContainText('已批准');
});

test('logging out in one tab ends the session in the other tab', async ({ browser }) => {
  const { ownerContext, owner } = await bootstrap(browser);
  const second = await ownerContext.newPage();
  await second.goto(owner.url());
  await expect(second.getByRole('heading', { name: '当前任务' })).toBeVisible();

  await owner.getByRole('button', { name: '退出登录' }).click();
  await expect(second.getByLabel('邮箱', { exact: true })).toBeVisible();

  // Reloading must not restore a session that was revoked in the other tab.
  await second.reload();
  await expect(second.getByLabel('邮箱', { exact: true })).toBeVisible();
});

test('editing the same constraint from two tabs keeps the stale input and resubmits', async ({
  browser,
}) => {
  const { designerContext, owner, designer } = await bootstrap(browser);
  await toDesignerWait(owner);
  const tabA = designer;
  await tabA.reload();
  const created = await submitConstraint(tabA, '并发约束');
  expect((await created).status()).toBe(200);

  const tabB = await designerContext.newPage();
  await tabB.goto(tabA.url());
  await expect(tabB.getByRole('heading', { name: '当前任务' })).toBeVisible();
  await expect(tabB.locator('.sidebar')).toContainText('并发约束');

  const first = await updateConstraint(tabA, '并发约束', '并发约束 A 版');
  expect((await first).status()).toBe(200);

  const second = await updateConstraint(tabB, '并发约束', '并发约束 B 版');
  expect((await second).status()).toBe(409);
  await expect(tabB.getByText(/输入已保留/)).toBeVisible();
  await expect(tabB.getByLabel('约束内容')).toHaveValue('并发约束 B 版');

  await expect(tabB.locator('.sidebar')).toContainText('并发约束 A 版');
  const retried = await updateConstraint(tabB, '并发约束 A 版', '并发约束 B 版');
  expect((await retried).status()).toBe(200);
  await expect(tabB.locator('.sidebar')).toContainText('并发约束 B 版');
});

test('deleting a question source image lets another tab reach the next step', async ({
  browser,
}) => {
  const { ownerContext, owner } = await bootstrap(browser);
  await write(owner, '启动分析', '/analysis-runs', 202);
  const tabA = owner;
  const tabB = await ownerContext.newPage();
  await tabB.goto(tabA.url());
  await expect(tabB.getByRole('heading', { name: '当前任务' })).toBeVisible();

  // Select two parts on different images so two detail groups exist.
  await tabA.getByRole('checkbox').nth(0).check();
  await tabA.getByRole('checkbox').nth(5).check();
  const broad = tabA.waitForResponse(
    (r) => r.url().endsWith('/answer') && r.request().method() !== 'GET',
  );
  await tabA.getByRole('button', { name: '提交回答', exact: true }).click();
  expect((await broad).status()).toBe(202);
  await expect(tabA.getByRole('button', { name: '喜欢', exact: true }).first()).toBeVisible();

  const label = await tabA.locator('.option span').first().innerText();
  const imageName = label.split(' · ')[0];
  const deletion = tabA.waitForResponse(
    (r) => r.request().method() === 'DELETE' && r.url().includes('/assets/'),
  );
  tabA.once('dialog', (dialog) => dialog.accept());
  await tabA.getByRole('button', { name: `删除 ${imageName}`, exact: true }).click();
  expect((await deletion).status()).toBe(200);

  // The other tab refreshes into the next valid question, not the deleted image.
  await tabB.reload();
  await expect(tabB.getByRole('button', { name: '喜欢', exact: true }).first()).toBeVisible();
  expect(await tabB.locator('fieldset').innerText()).not.toContain(imageName);
});

test('a refresh response arriving after logout cannot restore the session', async ({ browser }) => {
  const { ownerContext, owner } = await bootstrap(browser);
  const second = await ownerContext.newPage();
  await second.goto(owner.url());
  await expect(second.getByRole('heading', { name: '当前任务' })).toBeVisible();

  let refreshStarted!: () => void;
  const started = new Promise<void>((resolve) => {
    refreshStarted = resolve;
  });
  await owner.route('**/auth/refresh', async (route) => {
    const response = await route.fetch();
    refreshStarted();
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.fulfill({ response });
  });

  await owner.reload();
  await started;
  await second.getByRole('button', { name: '退出登录' }).click();
  await expect(owner.getByLabel('邮箱', { exact: true })).toBeVisible();

  // A late refresh response must not resurrect the revoked session.
  await owner.reload();
  await expect(owner.getByLabel('邮箱', { exact: true })).toBeVisible();
});
