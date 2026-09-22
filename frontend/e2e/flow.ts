import { expect, type Page } from '@playwright/test';

export const PASSWORD = 'local collaboration resilience password';
const PAGE_LABELS = {
  overview: '项目概览',
  inspiration: '灵感与偏好',
  negotiation: '设计协商',
  space: '空间方案',
  approval: '方案审批',
} as const;

export type WorkspacePageName = keyof typeof PAGE_LABELS;

/** Navigate the workspace shell to a page and wait for it to become current. */
export async function goToPage(page: Page, target: WorkspacePageName): Promise<void> {
  const button = page.getByRole('button', { name: PAGE_LABELS[target], exact: true });
  await button.click();
  await expect(button).toHaveAttribute('aria-current', 'page');
}


export async function register(page: Page, email: string): Promise<void> {
  await page.goto('/');
  await page.getByRole('tab', { name: '注册' }).click();
  await page.getByLabel('邮箱', { exact: true }).fill(email);
  await page.getByLabel('密码', { exact: true }).fill(PASSWORD);
  await page.getByLabel('确认密码', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: '注册', exact: true }).click();
  await expect(page.getByRole('heading', { name: '我的项目' })).toBeVisible();
}

export async function ownerCreatesProject(owner: Page): Promise<string> {
  await owner.getByLabel('预算金额（新加坡元 SGD）').fill('20000');
  await owner.getByLabel('同意处理参考图片（真实上传，模拟分析）').check();
  await owner.getByRole('button', { name: '创建', exact: true }).click();
  await owner.getByRole('button', { name: '生成项目码' }).click();
  const code = await owner.locator('.join-code code').innerText();
  await owner.getByRole('button', { name: /客厅/ }).click();
  await expect(owner.getByRole('heading', { name: '当前任务' })).toBeVisible();
  return code;
}

export async function designerJoins(designer: Page, code: string): Promise<void> {
  await designer.getByLabel('项目码', { exact: true }).fill(code);
  await designer.getByRole('button', { name: '加入', exact: true }).click();
  await expect(designer.getByRole('heading', { name: '当前任务' })).toBeVisible();
}

export async function write(
  page: Page,
  button: string,
  suffix: string,
  status = 200,
): Promise<void> {
  const response = page.waitForResponse(
    (r) => r.url().endsWith(suffix) && r.request().method() !== 'GET',
  );
  await page.getByRole('button', { name: button, exact: true }).click();
  const result = await response;
  expect(result.status(), await result.text()).toBe(status);
  const body = await result.json();
  await expect
    .poll(async () =>
      page
        .locator('.meta')
        .innerText()
        .then((text) => text.includes(`v${body.stateVersion ?? body.projectState?.stateVersion}`)),
    )
    .toBe(true);
}

export async function uploadAsset(page: Page, name: string): Promise<void> {
  await goToPage(page, 'inspiration');
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 1600;
    canvas.height = 1200;
    canvas.getContext('2d')!.fillRect(0, 0, 1600, 1200);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/assets') && r.request().method() !== 'GET',
  );
  await page
    .getByLabel('上传参考图片')
    .setInputFiles({ name, mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  const result = await response;
  expect(result.status(), await result.text()).toBe(201);
  const body = await result.json();
  await expect
    .poll(async () =>
      page
        .locator('.meta')
        .innerText()
        .then((text) => text.includes(`v${body.stateVersion}`)),
    )
    .toBe(true);
  await expect(page.getByRole('img', { name, exact: true })).toBeVisible();
}

export async function answerBroadAndDetails(owner: Page): Promise<void> {
  await goToPage(owner, 'inspiration');
  await write(owner, '启动分析', '/analysis-runs', 202);
  const parts = owner.getByRole('checkbox');
  const partCount = await parts.count();
  for (let index = 0; index < partCount; index++) await parts.nth(index).check();
  await write(owner, '提交回答', '/answer', 202);

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
}

export async function addExplicitPreferences(owner: Page): Promise<void> {
  await goToPage(owner, 'inspiration');
  for (const [dimension, value] of [
    ['style', 'warm modern'],
    ['material', 'natural stone'],
    ['layout', 'clear conversational seating'],
    ['furniture', 'compact rounded furniture'],
    ['mood', 'calm and welcoming'],
    ['function', 'conversation and reading'],
  ]) {
    await owner.getByLabel('偏好维度').selectOption(dimension);
    await owner.getByLabel('偏好内容').fill(value);
    await owner.getByRole('button', { name: '保存偏好', exact: true }).click();
    await expect(owner.getByLabel('偏好内容')).toHaveValue('');
    await expect(owner.locator('.sidebar')).toContainText(value);
  }
}

export async function toDesignerWait(owner: Page): Promise<void> {
  await answerBroadAndDetails(owner);
  await addExplicitPreferences(owner);
  await goToPage(owner, 'overview');
  await expect(owner.getByText('等待设计师反馈')).toBeVisible();
}

export async function designerAddConstraint(designer: Page, statement: string): Promise<void> {
  await goToPage(designer, 'negotiation');
  await designer.getByLabel('作用对象').fill('living_room');
  await designer.getByLabel('约束内容').fill(statement);
  await write(designer, '保存约束', '/constraints', 200);
}

export async function toAwaitingApproval(owner: Page, designer: Page): Promise<void> {
  await toDesignerWait(owner);
  await designer.reload();
  await designerAddConstraint(designer, '预算档位已在项目信息中确认');
  await write(designer, '提交设计师反馈', '/designer-reviews', 200);
  await goToPage(designer, 'approval');
  await expect(designer.getByText('方案版本 v1', { exact: false })).toBeVisible();
}
