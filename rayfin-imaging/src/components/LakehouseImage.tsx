import { useEffect, useState, type ImgHTMLAttributes } from 'react';

import { lakehouseUrl, loadViaProxy, type Slide, type TileAccess } from '@/lib/catalog';

interface LakehouseImageProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'src'> {
  access: TileAccess;
  slide: Slide;
  path: string;
}

/** An image stored in the Lakehouse, loaded directly (SAS) or through the Rayfin tile proxy. */
export function LakehouseImage({ access, slide, path, ...rest }: LakehouseImageProps) {
  const url = lakehouseUrl(access, slide, path);
  const [src, setSrc] = useState<string | undefined>(access.mode === 'sas' ? url : undefined);

  useEffect(() => {
    if (access.mode === 'sas') {
      setSrc(url);
      return;
    }
    let cancelled = false;
    loadViaProxy(url)
      .then((dataUrl) => !cancelled && setSrc(dataUrl))
      .catch((err) => console.error('Thumbnail load failed', err));
    return () => {
      cancelled = true;
    };
    // Only refetch when the logical file changes, not when the SAS rotates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [access.mode, slide.id, path]);

  return src ? <img src={src} {...rest} /> : <div className={rest.className} />;
}
