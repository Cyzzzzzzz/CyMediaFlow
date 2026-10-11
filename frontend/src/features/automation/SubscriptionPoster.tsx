import { Television } from "@phosphor-icons/react";
import { useState } from "react";
import { ArtworkImage } from "../../components/ArtworkImage";

export function SubscriptionPoster({ title, url, localUrl, priority = false }: { title: string; url?: string | null; localUrl?: string | null; priority?: boolean }) {
  const [failed, setFailed] = useState<string[]>([]);
  const remote = url ? `/api/v1/automation/poster?url=${encodeURIComponent(url)}&width=320` : null;
  const src = [localUrl, remote].find((item): item is string => Boolean(item) && !failed.includes(item!));
  return <div className="subscription-poster">
    {src ? <ArtworkImage src={src} alt={`${title} 海报`} priority={priority} onError={() => setFailed((old) => [...old, src])} /> : <div className="subscription-poster-placeholder"><Television size={34} weight="thin" /><span>{title || "番剧海报"}</span></div>}
  </div>;
}
