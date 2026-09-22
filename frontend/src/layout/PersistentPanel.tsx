import type { ReactNode } from 'react';

/**
 * A page panel that hides without unmounting, so in-progress form state and the
 * 3D editor (which the browser does not recreate cheaply) survive navigation.
 */
export function PersistentPanel({
  active,
  id,
  children,
}: {
  active: boolean;
  id: string;
  children: ReactNode;
}) {
  return (
    <section id={id} hidden={!active}>
      {children}
    </section>
  );
}
