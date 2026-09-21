/**
 * AlignSpace bridge for the local OpenPlan3D editor.
 *
 * Installed into the pinned upstream tree by scripts/fetch_openplan3d.sh. The
 * editor is embedded in an iframe by our frontend. This module:
 *   1. announces readiness to the parent,
 *   2. imports the parent's authoritative plan (optionally applying the saved
 *      floor material per room) and loads it into the editor store,
 *   3. posts the edited project back so the parent can persist it through the
 *      same permissioned, versioned backend API as the 2D panel.
 *
 * It never talks to an upstream cloud service; all traffic is a same-window
 * postMessage between the local editor and the local frontend.
 */
import { get } from 'svelte/store';
import {
  createDefaultProject,
  currentProject,
  loadProject,
  moveFurniture,
  updateRoom,
} from '$lib/stores/project';
import { importRoomPlan } from '$lib/utils/roomplanImport';

const PROTOCOL = 1;

// Our material option ids -> the editor's bundled floor textures.
const FLOOR_TEXTURES: Record<string, string> = {
  'floor.engineered-oak': 'light-oak',
  'floor.porcelain-tile': 'porcelain',
  'floor.vinyl-plank': 'vinyl',
  'floor.microcement': 'concrete',
  'wall.microcement': 'concrete',
};

function isEmbedded(): boolean {
  return typeof window !== 'undefined' && window.parent !== window;
}

function post(type: string, payload: Record<string, unknown> = {}): void {
  if (!isEmbedded()) return;
  window.parent.postMessage({ type, protocol: PROTOCOL, ...payload }, '*');
}

export function startAlignSpaceBridge(): void {
  if (!isEmbedded()) return;

  let suppressUntil = 0;
  let lastFingerprint: string | null = null;

  // Read-only introspection plus the two mutations used by automated
  // verification. They only touch this local editor's store.
  (window as unknown as { __alignspace?: unknown }).__alignspace = {
    protocol: PROTOCOL,
    snapshot: () => get(currentProject),
    moveFurniture: (id: string, position: { x: number; y: number }) =>
      moveFurniture(id, position),
    renameRoom: (roomId: string, name: string) => updateRoom(roomId, { name }),
  };

  window.addEventListener('message', (event: MessageEvent) => {
    if (event.source !== window.parent) return;
    const data = event.data as
      | {
          type?: string;
          protocol?: number;
          fingerprint?: string;
          handoff?: {
            sections?: unknown[];
            alignspaceRoomIds?: string[];
            alignspaceFloorMaterials?: Record<string, string>;
          };
        }
      | null;
    if (!data || data.type !== 'alignspace:space' || data.protocol !== PROTOCOL || !data.handoff) {
      return;
    }
    if (data.fingerprint && data.fingerprint === lastFingerprint) {
      // The parent re-sent the state we already imported; do not churn.
      post('alignspace:applied', {
        fingerprint: data.fingerprint,
        roomCount: get(currentProject)?.floors?.[0]?.rooms?.length ?? 0,
      });
      return;
    }
    try {
      const floor = importRoomPlan(data.handoff);
      const roomIds = data.handoff.alignspaceRoomIds ?? [];
      const materials = data.handoff.alignspaceFloorMaterials ?? {};
      floor.rooms.forEach((room, index) => {
        const roomId = roomIds[index];
        if (roomId) (room as { alignspaceRoomId?: string }).alignspaceRoomId = roomId;
        const materialId = roomId ? materials[roomId] : undefined;
        const texture = materialId ? FLOOR_TEXTURES[materialId] : undefined;
        if (texture) room.floorTexture = texture;
      });
      const project = createDefaultProject('AlignSpace 空间草稿');
      project.floors = [floor];
      project.activeFloorId = floor.id;
      suppressUntil = Date.now() + 2500;
      lastFingerprint = data.fingerprint ?? null;
      loadProject(project);
      post('alignspace:applied', {
        fingerprint: data.fingerprint,
        roomCount: floor.rooms.length,
      });
    } catch (error) {
      post('alignspace:error', { message: String(error) });
    }
  });

  let timer: ReturnType<typeof setTimeout> | undefined;
  currentProject.subscribe((project) => {
    if (!project || Date.now() < suppressUntil) return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      post('alignspace:project', { project: JSON.parse(JSON.stringify(project)) });
    }, 400);
  });

  post('alignspace:ready', {});
}
