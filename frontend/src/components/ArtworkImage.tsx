import { useEffect, useRef, useState, type ImgHTMLAttributes } from "react";

type Props = ImgHTMLAttributes<HTMLImageElement> & { priority?: boolean };

export function ArtworkImage({ src, priority = false, ...props }: Props) {
  const ref = useRef<HTMLImageElement>(null);
  const [visible, setVisible] = useState(priority || typeof IntersectionObserver === "undefined");

  useEffect(() => {
    if (visible || !ref.current) return;
    // Native lazy loading may fetch several screens of posters at once, delaying detail APIs.
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: "160px" });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [visible]);

  return <img {...props} ref={ref} src={visible ? src : undefined} loading={priority ? "eager" : "lazy"} decoding="async" fetchPriority={priority ? "high" : "auto"} />;
}
