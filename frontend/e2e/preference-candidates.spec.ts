import { expect, test } from '@playwright/test';
import { ownerCreatesProject, register, uploadAsset } from './flow';

test('a homeowner turns images and a description into a confirmed preference', async ({
  browser,
}) => {
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  try {
    await register(owner, `prefs-owner-${Date.now()}@example.com`);
    await ownerCreatesProject(owner);
    for (let index = 0; index < 3; index++) {
      await uploadAsset(owner, `prefs-${index}.png`);
    }

    const board = owner.getByRole('region', { name: '图片偏好候选' });
    await board.getByLabel('选择图片 prefs-0.png').check();
    await board
      .getByLabel('喜欢这张图的哪些部分')
      .fill('喜欢墙壁的颜色和样式');
    await board.getByRole('button', { name: '生成候选偏好' }).click();

    // The three facts stay visibly separate, and nothing is confirmed yet.
    await expect(board.getByText(/我提到的关注维度/)).toBeVisible();
    await expect(board.getByText('颜色、样式')).toBeVisible();
    await expect(board.getByText(/模型观察\/推断/)).toBeVisible();
    await expect(board.getByText(/已确认：/)).toHaveCount(0);

    // Confirming writes one formal preference, shown with its confirmed value.
    await board.getByRole('button', { name: '确认颜色候选' }).click();
    await expect(board.getByText(/已确认：/)).toBeVisible();

    // The decision survives a reload because it is stored on the backend.
    await owner.reload();
    const reloaded = owner.getByRole('region', { name: '图片偏好候选' });
    await expect(reloaded.getByText(/已确认：/)).toBeVisible();
    await expect(reloaded.getByRole('button', { name: '确认颜色候选' })).toHaveCount(0);
  } finally {
    await ownerContext.close();
  }
});
