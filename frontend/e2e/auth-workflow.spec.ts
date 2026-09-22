import { test, expect, type Page } from '@playwright/test';
import { goToPage } from './flow';

const password = 'local browser acceptance password';

async function register(page: Page, email: string) {
  await page.goto('/');
  await page.getByRole('tab', { name: '注册' }).click();
  await page.getByLabel('邮箱', { exact: true }).fill(email);
  await page.getByLabel('密码', { exact: true }).fill(password);
  await page.getByLabel('确认密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '注册', exact: true }).click();
  await expect(page.getByRole('heading', { name: '我的项目' })).toBeVisible();
}

async function write(page: Page, button: string, suffix: string, status = 200) {
  const response = page.waitForResponse((r) => r.url().endsWith(suffix) && r.request().method() !== 'GET');
  await page.getByRole('button', { name: button, exact: true }).click();
  const result = await response;
  expect(result.status(), await result.text()).toBe(status);
  // Every successful workflow write is followed by a fresh state read.
  await expect.poll(async () => {
    const body = await result.json();
    return page.locator('.meta').innerText().then((text) => text.includes(`v${body.stateVersion ?? body.projectState?.stateVersion}`));
  }).toBe(true);
}

async function uploadAsset(page: Page, name: string) {
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 1600;
    canvas.height = 1200;
    canvas.getContext('2d')!.fillRect(0, 0, 1600, 1200);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  const response = page.waitForResponse((r) => r.url().endsWith('/assets') && r.request().method() !== 'GET');
  await page.getByLabel('上传参考图片').setInputFiles({ name, mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  const result = await response;
  expect(result.status(), await result.text()).toBe(201);
  const body = await result.json();
  // Every successful upload is followed by a fresh state read.
  await expect.poll(async () => {
    return page.locator('.meta').innerText().then((text) => text.includes(`v${body.stateVersion}`));
  }).toBe(true);
  const preview = page.getByRole('img', { name, exact: true });
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBe(1600);
  expect((await preview.boundingBox())!.width).toBeLessThanOrEqual(360);
  await expect(page.getByRole('link', { name: `查看原图：${name}`, exact: true })).toHaveAttribute('href', /^blob:/);
}

test('two real accounts complete a shared brief, retain stale input and restore sessions', async ({ browser }, testInfo) => {
  const ownerContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5174' });
  const designerContext = await browser.newContext({ baseURL: 'http://127.0.0.1:5174' });
  const owner = await ownerContext.newPage();
  const designer = await designerContext.newPage();
  const errors: string[] = [];
  const authEvents: string[] = [];
  ownerContext.on('request', (request) => {
    if (request.url().includes('/v1/auth/')) authEvents.push(`request ${new URL(request.url()).pathname}`);
  });
  ownerContext.on('response', (response) => {
    if (response.url().includes('/v1/auth/')) authEvents.push(`response ${response.status()} ${new URL(response.url()).pathname}`);
  });
  ownerContext.on('requestfailed', (request) => {
    if (request.url().includes('/v1/auth/')) authEvents.push(`failed ${new URL(request.url()).pathname} ${request.failure()?.errorText}`);
  });
  for (const page of [owner, designer]) page.on('pageerror', (error) => errors.push(error.message));
  let refreshes = 0;
  owner.on('request', (request) => { if (request.url().endsWith('/auth/refresh')) refreshes++; });
  const ownerEmail = `owner-${Date.now()}@example.com`;
  try {
    await register(owner, ownerEmail);
    await register(designer, `designer-${Date.now()}@example.com`);
    await owner.getByLabel('预算金额（新加坡元 SGD）').fill('20000');
    await owner.getByLabel('同意处理参考图片（真实上传，模拟分析）').check();
    await owner.getByRole('button', { name: '创建', exact: true }).click();
    await owner.getByRole('button', { name: '生成项目码' }).click();
    const code = await owner.locator('.join-code code').innerText();
    await designer.getByLabel('项目码', { exact: true }).fill(code);
    await designer.getByRole('button', { name: '加入', exact: true }).click();
    await expect(designer.getByRole('heading', { name: '当前任务' })).toBeVisible();
    await owner.getByRole('button', { name: /客厅.*屋主/ }).click();
    const projectUrl = owner.url();
    await owner.reload();
    await expect(owner.getByRole('heading', { name: '当前任务' })).toBeVisible();
    expect(owner.url()).toBe(projectUrl);
    expect(refreshes).toBe(2); // initial anonymous restore + explicit reload

    await goToPage(owner, 'inspiration');
    for (let i = 0; i < 3; i++) await uploadAsset(owner, `room-${i}.png`);
    await uploadAsset(owner, 'to-delete.png');
    const deletion = owner.waitForResponse((r) => r.request().method() === 'DELETE' && r.url().includes('/assets/'));
    owner.once('dialog', (dialog) => dialog.accept());
    await owner.getByRole('button', { name: '删除 to-delete.png', exact: true }).click();
    expect((await deletion).status()).toBe(200);
    await expect(owner.getByRole('img', { name: 'to-delete.png', exact: true })).toHaveCount(0);
    await expect(owner.getByText('已删除', { exact: true })).toBeVisible();
    await write(owner, '启动分析', '/analysis-runs', 202);
    const parts = owner.getByRole('checkbox');
    const partCount = await parts.count();
    for (let index = 0; index < partCount; index++) await parts.nth(index).check();
    await write(owner, '提交回答', '/answer', 202);


    // Answer each per-part detail question by confirming the observed value.
    for (let index = 0; index < 12; index++) {
      const likes = owner.getByRole('button', { name: '喜欢', exact: true });
      if ((await likes.count()) === 0) break;
      const likeCount = await likes.count();
      for (let j = 0; j < likeCount; j++) await likes.nth(j).click();
      const answered = owner.waitForResponse(
        (r) => r.url().endsWith('/answer') && r.request().method() !== 'GET',
      );
      await owner.getByRole('button', { name: '提交回答', exact: true }).click();
      const response = await answered;
      expect(response.status(), await response.text()).toBe(202);
      const body = await response.json();
      if (body.waitReason === 'homeowner' && body.pendingQuestion) {
        await owner
          .getByText(body.pendingQuestion.text, { exact: true })
          .waitFor({ timeout: 15000 });
      } else {
        await goToPage(owner, 'overview');
        await owner.getByText('等待设计师反馈').waitFor({ timeout: 15000 });
        break;
      }
    }

    await goToPage(owner, 'inspiration');
    for (const [dimension, value] of [
      ['style', 'warm modern'], ['material', 'natural stone'],
      ['layout', 'clear conversational seating'],
      ['furniture', 'compact rounded furniture'], ['mood', 'calm and welcoming'],
      ['function', 'conversation and reading'],
    ]) {
      await owner.getByLabel('偏好维度').selectOption(dimension);
      await owner.getByLabel('偏好内容').fill(value);
      await owner.getByRole('button', { name: '保存偏好', exact: true }).click();
      await expect(owner.getByLabel('偏好内容')).toHaveValue('');
      await expect(owner.locator('.sidebar')).toContainText(value);
    }
    await goToPage(owner, 'overview');
    await expect(owner.getByText('等待设计师反馈')).toBeVisible();

    // Designer enters a real constraint linked to a confirmed preference.
    await designer.reload();
    await goToPage(designer, 'negotiation');
    await designer.getByLabel('作用对象').fill('worktop');
    await designer.getByLabel('关联偏好').selectOption('manual-material');
    await designer.getByLabel('约束内容').fill('天然石材工作台超出当前预算档位');
    await designer.getByLabel('约束理由').fill('改用石材效果饰面');
    await designer.getByLabel('不兼容取值（逗号分隔）').fill('natural stone');
    await write(designer, '保存约束', '/constraints', 200);
    await write(designer, '提交设计师反馈', '/designer-reviews', 202);
    await goToPage(designer, 'overview');
    await expect(designer.getByText('等待屋主回答')).toBeVisible();

    await owner.reload();
    await goToPage(owner, 'inspiration');
    await expect(owner.locator('.question-text')).toContainText('trade-off');
    await owner.getByLabel('您的回答').fill('Use the lower-cost stone-effect finish.');
    await write(owner, '提交回答', '/answer');
    await goToPage(owner, 'approval');
    await expect(owner.getByText('方案版本 v1', { exact: false })).toBeVisible();
    await designer.reload();
    await goToPage(designer, 'approval');
    await expect(designer.getByLabel('方案目标')).toBeVisible();

    // Keep the owner's snapshot stale while the designer changes the real backend.
    await owner.route('**/state', (route) => route.abort());
    await owner.getByLabel('方案目标').fill('屋主尚未提交的修改');
    await designer.getByLabel('方案目标').fill('Designer updated goals');
    await designer.getByRole('button', { name: '保存方案修改' }).click();
    await expect(designer.getByText('方案版本 v2', { exact: false })).toBeVisible();
    await owner.unroute('**/state');
    // No focus event in headless mode; the next deliberate submit still uses v1.
    const stale = owner.waitForResponse((r) => r.request().method() === 'PATCH');
    await owner.getByRole('button', { name: '保存方案修改' }).click();
    expect((await stale).status()).toBe(409);
    await expect(owner.getByText(/输入已保留/)).toBeVisible();
    await expect(owner.getByText('方案版本 v2', { exact: false })).toBeVisible();
    await expect(owner.getByLabel('方案目标')).toHaveValue('屋主尚未提交的修改');
    await owner.getByRole('button', { name: '保存方案修改' }).click();
    await expect(owner.getByText('方案版本 v3', { exact: false })).toBeVisible();
    await expect(owner.getByLabel('方案目标')).toHaveValue('屋主尚未提交的修改');
    await designer.reload();
    await expect(designer.getByText('方案版本 v3', { exact: false })).toBeVisible();
    await expect(designer.getByLabel('方案目标')).toHaveValue('屋主尚未提交的修改');
    await write(owner, '批准此版本', '/approvals');
    // The designer should see the owner's approval through visible polling.
    await expect(designer.getByText('屋主已批准 v3')).toBeVisible();
    await write(designer, '批准此版本', '/approvals');
    await expect(owner.getByText('设计师已批准 v3')).toBeVisible();
    await expect(owner.locator('.meta')).toContainText('已批准');

    // Post-approval constraint change: brief becomes stale, must regenerate before re-approval.
    await goToPage(designer, 'negotiation');
    await designer.getByLabel('约束内容').fill('追加的预算约束');
    await write(designer, '保存约束', '/constraints', 200);
    await goToPage(designer, 'approval');
    await expect(designer.getByText('方案已过时，请重新生成后再审批。')).toBeVisible();
    await expect(designer.getByRole('button', { name: '批准此版本' })).toHaveCount(0);
    await write(designer, '重新生成方案', '/realign', 200);
    await expect(designer.getByText('方案版本 v4', { exact: false })).toBeVisible();
    await owner.reload();
    await expect(owner.getByText('方案版本 v4', { exact: false })).toBeVisible();
    await write(owner, '批准此版本', '/approvals');
    await expect(designer.getByText('屋主已批准 v4')).toBeVisible();
    await write(designer, '批准此版本', '/approvals');
    await expect(owner.getByText('设计师已批准 v4')).toBeVisible();
    await expect(owner.locator('.meta')).toContainText('已批准');

    await owner.screenshot({ path: testInfo.outputPath('workspace-desktop.png'), fullPage: true });
    await owner.setViewportSize({ width: 390, height: 844 });
    expect(await owner.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await owner.screenshot({ path: testInfo.outputPath('workspace-mobile.png'), fullPage: true });

    const secondTab = await ownerContext.newPage();
    await secondTab.goto(projectUrl);
    await expect(secondTab.getByRole('heading', { name: '当前任务' })).toBeVisible();
    await owner.getByRole('button', { name: '退出登录' }).click();
    await expect(secondTab.getByLabel('邮箱', { exact: true })).toBeVisible();
    await owner.reload();
    await expect(owner.getByLabel('邮箱', { exact: true })).toBeVisible();
    const refreshesBeforeLogin = refreshes;
    await owner.getByLabel('邮箱', { exact: true }).fill(ownerEmail);
    await owner.getByLabel('密码', { exact: true }).fill(password);
    await owner.getByRole('button', { name: '登录', exact: true }).click();
    await expect(owner.getByRole('heading', { name: '我的项目' })).toBeVisible();
    await owner.setViewportSize({ width: 1280, height: 900 });
    await owner.getByRole('button', { name: /客厅.*屋主/ }).click();
    await goToPage(owner, 'approval');
    await expect(owner.getByText('设计师已批准 v4')).toBeVisible();
    expect(refreshes).toBe(refreshesBeforeLogin);
    await expect(designer.getByRole('navigation', { name: '工作区导航' })).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    await testInfo.attach('auth-request-statuses', { body: authEvents.join('\n'), contentType: 'text/plain' });
    await ownerContext.close().catch(() => undefined);
    await designerContext.close().catch(() => undefined);
  }
});
