export type AutomationConfig = {
  enabled: boolean; interval_minutes: number; qb_url: string; qb_username: string;
  qb_save_root: string; rss_proxy_url: string; qb_password_configured: boolean;
  default_exclude_keywords: string[];
};
export type Feed = {
  id: number; name: string; url: string; enabled: boolean; status: string;
  last_checked_at: string | null; last_error: string | null;
};
export type SubscriptionDraft = {
  title: string; folder_name: string;
  aliases: string[]; season: number; episode_offset: number;
  preferred_group: string | null; preferred_resolution: string | null;
  exclude_keywords: string[]; enabled: boolean;
  season_offset: number; preferred_subtitle: "CHS" | "CHT" | null;
  archived: boolean; poster_url: string | null; year: number | null;
  source_title: string; source: string | null; subtitle: string | null;
  resolution: string | null; release_group: string | null;
  air_weekday: number | null; provider: "bangumi" | "tmdb" | null; provider_id: string | null;
};
export type Subscription = SubscriptionDraft & {
  id: number; feed_id: number; local_poster_url?: string | null;
};
export type SubscriptionMatch = {
  provider: "bangumi" | "tmdb"; external_id: string; title: string;
  original_title: string | null; year: number | null; image_url: string | null;
};
export type FeedCandidate = {
  rule: SubscriptionDraft; entry_count: number; examples: string[];
  matches: SubscriptionMatch[]; warning: string | null;
  versions?: number[]; subtitle_variants?: (string | null)[];
};
export type FeedAnalysis = {
  candidates: FeedCandidate[]; total_entries: number; unrecognized: number; truncated: boolean;
};
export type ReleaseAnalysis = {
  title: string | null; season: number | null; episode: number | null;
  group: string | null; resolution: string | null; confidence: number; warnings: string[];
  version?: number | null; subtitle?: string | null;
};
export type Release = {
  id: number; feed_id: number; title: string; analysis: ReleaseAnalysis;
  decision: string; reason: string | null;
};
export type Download = {
  id: number; release_id: number; subscription_id: number;
  torrent_hash: string | null; state: string; progress: number;
  error: string | null; save_path: string; created_at: string;
};
export type Event = {
  id: number; kind: string; message: string; feed_id: number | null;
  download_id: number | null; created_at: string;
};
