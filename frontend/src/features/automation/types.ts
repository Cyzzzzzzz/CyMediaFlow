export type AutomationConfig = {
  enabled: boolean; interval_minutes: number; qb_url: string; qb_username: string;
  qb_save_root: string; rss_proxy_url: string; qb_password_configured: boolean;
};
export type Feed = {
  id: number; name: string; url: string; enabled: boolean; status: string;
  last_checked_at: string | null; last_error: string | null;
};
export type Subscription = {
  id: number; feed_id: number; title: string; folder_name: string;
  aliases: string[]; season: number; episode_offset: number;
  preferred_group: string | null; preferred_resolution: string | null;
  exclude_keywords: string[]; enabled: boolean;
};
export type ReleaseAnalysis = {
  title: string | null; season: number | null; episode: number | null;
  group: string | null; resolution: string | null; confidence: number; warnings: string[];
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
