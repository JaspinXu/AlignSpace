import { expect, test } from '@playwright/test';
import { ownerCreatesProject, register, uploadAsset } from './flow';

test('five-page navigation keeps drafts, survives refresh/back and fits 320px', async ({
  browser,
}) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await register(page, `studio-${Date.now()}@example.com`);
    await ownerCreatesProject(page);

    // Overview is the default landing page.
    await expect(page.getByRole('heading', { name: '当前任务' })).toBeVisible();

    // Navigate to inspiration and start an unsaved preference.
    await page.getByRole('button', { name: '灵感与偏好', exact: true }).click();
    await expect(page).toHaveURL(/page=inspiration/);
    await expect(page.getByRole('heading', { name: '灵感与偏好' })).toBeVisible();
    await page.getByLabel('偏好内容').fill('暖白与橄榄绿');

    // Switching pages keeps the draft; the hidden page is not in the a11y tree.
    await page.getByRole('button', { name: '方案审批', exact: true }).click();
    await expect(page).toHaveURL(/page=approval/);
    await expect(page.getByRole('textbox', { name: '偏好内容' })).toHaveCount(0);
    await page.getByRole('button', { name: '灵感与偏好', exact: true }).click();
    await expect(page.getByLabel('偏好内容')).toHaveValue('暖白与橄榄绿');

    // Browser back/forward follows the page history (last entry was inspiration).
    await page.getByRole('button', { name: '空间方案', exact: true }).click();
    await expect(page).toHaveURL(/page=space/);
    await page.goBack();
    await expect(page).toHaveURL(/page=inspiration/);
    await page.goForward();
    await expect(page).toHaveURL(/page=space/);

    // Refresh keeps the selected page.
    await page.reload();
    await expect(page).toHaveURL(/page=space/);
    await expect(page.getByRole('heading', { name: '空间方案' })).toBeVisible();

    // Desktop, tablet and phone screenshots plus a 320px overflow check.
    for (const width of [1440, 820, 390, 320]) {
      await page.setViewportSize({ width, height: 820 });
      await page.screenshot({ path: `test-results/studio-${width}.png`, fullPage: true });
    }
    await page.setViewportSize({ width: 320, height: 780 });
    const fits = await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    );
    expect(fits).toBe(true);

    // Mobile menu opens, closes on Escape and returns focus to the trigger.
    await page.setViewportSize({ width: 390, height: 780 });
    const trigger = page.getByRole('button', { name: '菜单' });
    await trigger.click();
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await page.keyboard.press('Escape');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await expect(trigger).toBeFocused();
  } finally {
    await context.close();
  }
});


test('captures login, projects and the five pages with real images', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.goto('/');
    await page.screenshot({ path: 'test-results/studio-login.png', fullPage: true });
    await register(page, `studio-visual-${Date.now()}@example.com`);
    await page.screenshot({ path: 'test-results/studio-projects-empty.png', fullPage: true });

    await ownerCreatesProject(page);
    await page.screenshot({ path: 'test-results/studio-page-overview.png', fullPage: true });

    for (let index = 0; index < 3; index++) {
      await uploadAsset(page, `studio-real-${index}.png`);
    }
    const pages = [
      ['overview', '项目概览'],
      ['inspiration', '灵感与偏好'],
      ['negotiation', '设计协商'],
      ['space', '空间方案'],
      ['approval', '方案审批'],
    ] as const;
    for (const [name, label] of pages) {
      await page.getByRole('button', { name: label, exact: true }).click();
      await page.screenshot({ path: `test-results/studio-page-${name}.png`, fullPage: true });
    }

    await page.getByRole('button', { name: '返回我的项目' }).click();
    await page.screenshot({ path: 'test-results/studio-projects-list.png', fullPage: true });
  } finally {
    await context.close();
  }
});
