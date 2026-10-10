import { ImageBroken } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { imageSource } from "../../api/images";
import type { MediaItem } from "../../api/types";
import { ArtworkImage } from "../../components/ArtworkImage";

type Props = { item: MediaItem; selected: boolean; priority?: boolean; onOpen: (item: MediaItem) => void };
const statusText = { matched: "已识别", configured: "已配置", unconfigured: "待匹配" } as const;

export function PosterCard({ item, selected, priority = false, onOpen }: Props) {
  const [imageFailed, setImageFailed] = useState(false);
  const poster = imageSource(item.poster_url);
  useEffect(() => setImageFailed(false), [poster]);
  return <button className={`poster-card ${selected ? "selected" : ""}`} type="button" onClick={() => onOpen(item)}>
    <span className="poster-frame">
      {poster && !imageFailed
        ? <ArtworkImage src={poster} alt="" priority={priority} onError={() => setImageFailed(true)} />
        : <span className="poster-unavailable" aria-hidden="true"><ImageBroken size={28} weight="duotone" /></span>}
    </span>
    <span className="poster-title" title={item.title}>{item.title}</span>
    <span className={`poster-status ${item.status}`}><i /> {statusText[item.status]}</span>
  </button>;
}
