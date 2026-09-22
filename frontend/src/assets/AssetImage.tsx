import { useEffect, useState } from 'react';

import type { ApiClient } from '../api';
import type { Asset } from '../types';

/** Load a protected asset as an object URL and revoke it on unmount. */
export function useAssetUrl(client: ApiClient, projectId: string, asset: Asset): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (asset.deleted) return;
    let active = true;
    let objectUrl: string | null = null;
    client
      .blob(`/v1/projects/${projectId}/assets/${asset.id}/content`)
      .then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [client, projectId, asset.id, asset.deleted]);
  return url;
}

export function AssetImage({
  client,
  projectId,
  asset,
  className = 'asset-image',
  decorative = false,
}: {
  client: ApiClient;
  projectId: string;
  asset: Asset;
  className?: string;
  /** Decorative use (e.g. behind a labelled checkbox) keeps the label single. */
  decorative?: boolean;
}) {
  const url = useAssetUrl(client, projectId, asset);
  if (asset.deleted) return <span className="asset-missing">已删除</span>;
  if (!url) return <span className="asset-image asset-image--empty" aria-hidden="true" />;
  return (
    <img
      className={className}
      src={url}
      alt={decorative ? '' : asset.originalFilename}
      aria-hidden={decorative || undefined}
      loading="lazy"
    />
  );
}
