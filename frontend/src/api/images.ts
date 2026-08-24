export function imageSource(url: string | null): string | null {
  if (!url || url.startsWith("/")) return url;
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
