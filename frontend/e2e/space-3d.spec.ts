import { expect, test } from '@playwright/test';
import { ownerCreatesProject, register, uploadAsset } from './flow';

/**
 * Real OpenPlan3D browser acceptance. Skipped unless the pinned upstream
 * checkout is installed (scripts/fetch_openplan3d.sh && npm install).
 */
test('the 3D editor imports the plan, shows the material and syncs edits back', async ({
  browser,
}) => {
  test.skip(process.env.ALIGNSPACE_3D_AVAILABLE !== '1', 'OpenPlan3D checkout is not installed');
  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  try {
    await register(owner, `space3d-owner-${Date.now()}@example.com`);
    await ownerCreatesProject(owner);

    // One room.
    const space = owner.getByRole('region', { name: '空间草稿' });
    const roomCreated = owner.waitForResponse(
      (response) => response.url().endsWith('/space/rooms') && response.request().method() === 'POST',
    );
    await space.getByLabel('房间名称').fill('客厅');
    await space.getByRole('button', { name: '添加房间' }).click();
    expect((await roomCreated).status()).toBe(200);

    // Confirmed floor "laying" preference overridden to an exactly supported value.
    for (let index = 0; index < 3; index++) {
      await uploadAsset(owner, `space3d-${index}.png`);
    }
    const board = owner.getByRole('region', { name: '图片偏好候选' });
    await board.getByLabel('选择图片 space3d-0.png').check();
    await board.getByLabel('喜欢这张图的哪些部分').fill('喜欢地板的铺设方式');
    await board.getByRole('button', { name: '生成候选偏好' }).click();
    await board.getByLabel('自定义取值 铺设方式').fill('herringbone');
    await board.getByRole('button', { name: '确认铺设方式候选' }).click();
    await expect(board.getByText(/已确认：herringbone/)).toBeVisible();

    await owner.reload();
    const shared = owner.getByRole('region', { name: '空间草稿' });
    await shared.getByLabel('已确认地板偏好').selectOption({ index: 1 });
    // An unrenderable laying pattern must be acknowledged before binding.
    await expect(shared.getByText(/3D 预览暂不支持「人字拼」/)).toBeVisible();
    await shared.getByLabel(/我理解 3D 预览不会呈现该铺法/).check();
    await shared.getByLabel('房间', { exact: true }).selectOption({ index: 1 });
    const bound = owner.waitForResponse(
      (response) => response.url().endsWith('/space/bindings') && response.request().method() === 'POST',
    );
    await shared.getByRole('button', { name: '绑定到房间' }).click();
    expect((await bound).status()).toBe(200);
    const applied = owner.waitForResponse(
      (response) => response.url().includes('/space/bindings/') && response.url().endsWith('/apply'),
    );
    await shared.getByRole('button', { name: '应用材质到空间' }).click();
    expect((await applied).status()).toBe(200);
    await expect(shared.getByText(/已应用到 v2/)).toBeVisible();

    // One furniture object to move from the 3D editor.
    await shared.getByRole('button', { name: '客厅' }).click();
    const objectCreated = owner.waitForResponse(
      (response) => response.url().endsWith('/space/objects') && response.request().method() === 'POST',
    );
    await shared.getByRole('button', { name: '添加家具' }).click();
    expect((await objectCreated).status()).toBe(200);
    const objectRect = shared.locator('[data-testid^="object-"]').first();
    await expect(objectRect).toBeVisible();
    const objectId = (await objectRect.getAttribute('data-testid'))!.replace('object-', '');
    const beforeX = Number(await objectRect.getAttribute('x'));

    // Open the local 3D editor and wait for the bridge handshake.
    await shared.getByRole('button', { name: '打开 3D 预览' }).click();
    const element = await owner.locator('iframe[title="OpenPlan3D 本地预览"]').elementHandle();
    expect(element).not.toBeNull();
    const editor = await element!.contentFrame();
    expect(editor).not.toBeNull();
    await editor!.waitForFunction(() => Boolean((window as any).__alignspace?.snapshot?.()));

    // The plan imported with the saved floor material and our room identity.
    const snapshot = await editor!.evaluate(() => {
      const project = (window as any).__alignspace.snapshot();
      const floor = project?.floors?.find((f: any) => f.id === project.activeFloorId);
      return {
        roomCount: floor?.rooms?.length ?? 0,
        firstRoom: floor?.rooms?.[0]
          ? {
              name: floor.rooms[0].name,
              floorTexture: floor.rooms[0].floorTexture,
              alignspaceRoomId: floor.rooms[0].alignspaceRoomId,
            }
          : null,
        furnitureIds: (floor?.furniture ?? []).map((item: any) => item.id),
      };
    });
    expect(snapshot.roomCount).toBe(1);
    expect(snapshot.firstRoom?.name).toBe('客厅');
    expect(snapshot.firstRoom?.floorTexture).toBe('light-oak');
    expect(snapshot.firstRoom?.alignspaceRoomId).toBeTruthy();
    expect(snapshot.furnitureIds).toContain(objectId);

    // A real store mutation in the editor must flow back through our controlled
    // API. No time window: the bridge only filters the import it just applied.
    await editor!.evaluate((id) => {
      (window as any).__alignspace.moveFurniture(id, { x: 150, y: 350 });
    }, objectId);
    await expect(objectRect).not.toHaveAttribute('x', String(beforeX), { timeout: 15000 });

    // The edit persists across a reload (backend authority).
    await owner.reload();
    const persisted = owner
      .getByRole('region', { name: '空间草稿' })
      .locator(`[data-testid="object-${objectId}"]`);
    await expect(persisted).toBeVisible();
    await expect(persisted).not.toHaveAttribute('x', String(beforeX));

    // Reopening the 3D editor must place the object at the saved position, not
    // reset it to the room centre.
    await owner.getByRole('region', { name: '空间草稿' }).getByRole('button', { name: '打开 3D 预览' }).click();
    const reopenedElement = await owner.locator('iframe[title="OpenPlan3D 本地预览"]').elementHandle();
    const reopened = await reopenedElement!.contentFrame();
    await reopened!.waitForFunction(() => Boolean((window as any).__alignspace?.snapshot?.()));
    const repositioned = await reopened!.evaluate((id) => {
      const project = (window as any).__alignspace.snapshot();
      const floor = project?.floors?.find((f: any) => f.id === project.activeFloorId);
      const item = (floor?.furniture ?? []).find((f: any) => f.id === id);
      return item ? { x: Math.round(item.position.x), y: Math.round(item.position.y) } : null;
    }, objectId);
    expect(repositioned).toEqual({ x: 150, y: 350 });
  } finally {
    await ownerContext.close();
  }
});
