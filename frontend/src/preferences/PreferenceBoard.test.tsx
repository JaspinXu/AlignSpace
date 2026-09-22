import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ApiClient } from '../api';
import type { Asset, Candidate, CandidateBoard, DesignEntry } from '../types';
import { PreferenceBoard } from './PreferenceBoard';

const asset: Asset = {
  id: 'asset-1',
  originalFilename: 'living-room.png',
  mediaType: 'image/png',
  sizeBytes: 10,
  sha256: 'aaa',
  deleted: false,
  deletedAt: null,
};

function candidate(overrides: Partial<Candidate>): Candidate {
  return {
    id: 'cand-colour',
    entryId: 'entry-1',
    dimension: 'colour',
    certainty: 'inferred',
    proposedValue: 'warm beige',
    confirmedValue: null,
    status: 'proposed',
    attributeId: null,
    humanEdited: false,
    evidence: [],
    ...overrides,
  };
}

function entry(overrides: Partial<DesignEntry> = {}): DesignEntry {
  return {
    id: 'entry-1',
    analysisRunId: 'run-1',
    sourceAssetId: 'asset-1',
    sourceAvailable: true,
    targetElement: 'wall',
    attentionDimensions: ['colour', 'material'],
    note: '',
    status: 'open',
    candidates: [
      candidate({}),
      candidate({
        id: 'cand-material',
        dimension: 'material',
        certainty: 'uncertain',
        proposedValue: null,
      }),
    ],
    ...overrides,
  };
}

function board(designEntry: DesignEntry = entry()): CandidateBoard {
  return {
    stateVersion: 3,
    runs: [
      {
        id: 'run-1',
        status: 'completed',
        description: '喜欢墙壁的颜色和材质',
        providerMode: 'mock',
        model: 'mock-deterministic',
        promptVersion: 'candidate-prompt-v1',
        schemaVersion: '1.0.0',
        thirdPartyConsent: false,
        inputAssets: [{ assetId: 'asset-1', sha256: 'aaa' }],
        inputFingerprint: 'fp',
        stale: false,
        error: null,
        entries: [designEntry],
      },
    ],
  };
}

function setup(initial: CandidateBoard, role: 'homeowner' | 'designer' = 'homeowner') {
  const execute = vi.fn(async (_write: { path: string; method: string; body: string }) => initial);
  const client = {
    get: vi.fn(async () => initial),
    blob: vi.fn(async () => new Blob()),
    execute,
  } as unknown as ApiClient;
  render(
    <PreferenceBoard
      client={client}
      projectId="p1"
      role={role}
      assets={[asset]}
      stateVersion={initial.stateVersion}
    />,
  );
  return { execute };
}

describe('PreferenceBoard', () => {
  it('keeps attention, model inference and confirmation visibly separate', async () => {
    setup(board());
    expect(await screen.findByText(/我提到的关注维度/)).toBeVisible();
    expect(screen.getByText(/模型观察\/推断/)).toBeVisible();
    expect(screen.getByText('颜色、材质')).toBeVisible();
    // An undetermined material must read as uncertain rather than a guess.
    expect(screen.getByText('不确定')).toBeVisible();
  });

  it('does not let a designer analyse or decide', async () => {
    setup(board(), 'designer');
    await screen.findByText(/我提到的关注维度/);
    expect(screen.queryByRole('button', { name: '生成候选偏好' })).toBeNull();
    expect(screen.queryByRole('button', { name: '确认颜色候选' })).toBeNull();
  });

  it('confirms a candidate through the versioned envelope', async () => {
    const { execute } = setup(board());
    await userEvent.click(await screen.findByRole('button', { name: '确认颜色候选' }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    const write = execute.mock.calls[0][0];
    expect(write.path).toBe('/v1/projects/p1/candidates/cand-colour/confirm');
    expect(JSON.parse(write.body).expectedStateVersion).toBe(3);
  });

  it('sends a custom value when the homeowner overrides a proposal', async () => {
    const { execute } = setup(board());
    const input = await screen.findByLabelText('自定义取值 颜色');
    await userEvent.type(input, 'microcement');
    await userEvent.click(screen.getByRole('button', { name: '确认颜色候选' }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    const write = execute.mock.calls[0][0];
    expect(JSON.parse(write.body).data.value).toBe('microcement');
  });

  it('blocks confirmation when the source image is gone', async () => {
    setup(
      board(
        entry({
          status: 'source_deleted',
          sourceAvailable: false,
          candidates: [candidate({ certainty: 'uncertain', proposedValue: null })],
        }),
      ),
    );
    const note = await screen.findByRole('note');
    expect(note).toHaveTextContent('来源图片已删除');
    expect(screen.getByRole('button', { name: '确认颜色候选' })).toBeDisabled();
  });

  it('runs analysis with the selected images, description and consent', async () => {
    const { execute } = setup(board({ ...entry(), candidates: [] }));
    await userEvent.click(await screen.findByLabelText('选择图片 living-room.png'));
    await userEvent.type(
      screen.getByLabelText('喜欢这张图的哪些部分'),
      '喜欢床的颜色和样式',
    );
    await userEvent.click(
      screen.getByLabelText(/同意将参考图片和描述发送至第三方模型服务/),
    );
    await userEvent.click(screen.getByRole('button', { name: '生成候选偏好' }));
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(1));
    const write = execute.mock.calls[0][0];
    expect(write.path).toBe('/v1/projects/p1/preference-analyses');
    expect(JSON.parse(write.body).data).toEqual({
      assetIds: ['asset-1'],
      description: '喜欢床的颜色和样式',
      thirdPartyConsent: true,
    });
  });
});
