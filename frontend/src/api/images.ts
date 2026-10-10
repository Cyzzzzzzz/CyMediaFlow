export function imageSource(url: string | null, width: 160 | 320 | 640 = 320): string | null {
  if (!url) return url;
  if (url.startsWith("/api/v1/media/") && /\/(poster|artwork)([/?]|$)/.test(url)) {
    const [path, query] = url.split("?", 2);
    const params = new URLSearchParams(query);
    params.set("width", String(width));
    return `${path}?${params.toString()}`;
  }
  if (url.startsWith("/")) return url;
  try {
    const parsed = new URL(url);
    if (parsed.hostname === "lain.bgm.tv") {
      return `/api/v1/images/bangumi?url=${encodeURIComponent(url)}`;
    }
  } catch {
    return null;
  }
  return url;
}
