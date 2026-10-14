import { apiRequest } from "../../api/client";
import type { Release, Subscription, SubscriptionDraft } from "./types";

const base = "/api/v1/automation";
export const post = <T>(path: string, body: unknown = {}) =>
  apiRequest<T>(base + path, { method: "POST", body: JSON.stringify(body) });
export type Source = {
  id: string;
  name: string;
  kind: "rss" | "torznab";
  enabled: boolean;
  address?: string;
  url?: string | null;
  api_key?: string | null;
  api_key_configured?: boolean;
};
export type FeatureSettings = {
  sources: Source[];
  aria2_url: string;
  aria2_save_root: string;
  aria2_secret_configured: boolean;
  webhook_enabled: boolean;
  webhook_url_configured: boolean;
  webhook_secret_configured: boolean;
  webhook_events: string[];
  llm_enabled: boolean;
  llm_url: string;
  llm_model: string;
  llm_api_key_configured: boolean;
  version_auto_check: boolean;
  calendar_auto_refresh?: boolean;
};
export type SearchResult = {
  source_id?: string;
  query: string;
  feed_id?: number;
  updated_at?: string;
  items: Release[];
};
export type DownloadPreview = {
  title: string;
  target_title: string;
  season: number;
  episode: number | null;
  existing_job?: number;
  confirmed: boolean;
  state?: string;
};
export type Mapping = { source: string; season: number; episode: number };
export type FilePlan = {
  files: { source: string; target: string }[];
  executed: boolean;
  state?: string;
};
export type Backfill = {
  subscription_id: number;
  local: number[];
  queued: number[];
  expected_known: boolean;
  missing: {
    episode: number;
    candidate: { release_id: number; title: string } | null;
  }[];
  offset_suggestion: {
    episode_offset: number;
    reason: string;
    confidence: string;
  } | null;
};
export type Orphan = {
  hash: string;
  name: string;
  save_path: string;
  progress: number;
};
export type Inbox = {
  unread: number;
  items: {
    id: number;
    kind: string;
    message: string;
    created_at: string;
    read: boolean;
  }[];
};
export type Version = {
  current: string;
  latest: string | null;
  checked_at: string | null;
  url?: string;
};
export const featureApi = {
  settings: () => apiRequest<FeatureSettings>(base + "/features/settings"),
  saveSettings: (body: unknown) =>
    apiRequest<FeatureSettings>(base + "/features/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  searchCache: () => apiRequest<SearchResult>(base + "/search"),
  search: (source_id: string, query: string) =>
    post<SearchResult>("/search", { source_id, query }),
  subscribe: (feed_id: number, rule: SubscriptionDraft) =>
    post<Subscription>("/search/subscribe", { feed_id, rule }),
  download: (
    id: number,
    subscription_id: number,
    confirm: boolean,
    episode: number | null,
  ) =>
    post<DownloadPreview>(`/releases/${id}/download`, {
      subscription_id,
      confirm,
      episode,
    }),
  skip: (id: number) => post(`/releases/${id}/skip`),
  suggest: (title: string, refresh = false) =>
    post<{
      suggestion: {
        title: string;
        episode: number | null;
        season: number | null;
      };
      requires_review: boolean;
    }>("/parser/suggest", { title, refresh }),
  action: (id: number, action: string, confirm = false) =>
    post<FilePlan>(`/downloads/${id}/action`, { action, confirm }),
  files: (id: number) =>
    apiRequest<{ name: string }[]>(base + `/downloads/${id}/files`),
  organize: (id: number, mappings: Mapping[], confirm: boolean) =>
    post<FilePlan>(`/downloads/${id}/organize`, { mappings, confirm }),
  revision: (
    id: number,
    previous_id: number,
    confirm: boolean,
    restore = false,
  ) =>
    post<FilePlan>(`/downloads/${id}/revision${restore ? "/restore" : ""}`, {
      previous_id,
      confirm,
    }),
  backfill: (id: number) =>
    apiRequest<Backfill>(base + `/subscriptions/${id}/backfill`),
  collect: (id: number, release_ids: number[]) =>
    post(`/subscriptions/${id}/backfill`, { release_ids, confirm: true }),
  orphans: () => apiRequest<Orphan[]>(base + "/orphans"),
  adopt: (torrent_hash: string, subscription_id: number, episode: number) =>
    post("/orphans/adopt", {
      torrent_hash,
      subscription_id,
      episode,
      confirm: true,
    }),
  calendar: () =>
    apiRequest<{ items: Subscription[]; updated_at: string | null }>(
      base + "/calendar",
    ),
  refreshCalendar: () =>
    post<{ items: Subscription[]; updated_at: string | null }>(
      "/calendar/refresh",
    ),
  notifications: () => apiRequest<Inbox>(base + "/notifications"),
  markRead: (through: number) => post("/notifications/read", { through }),
  version: () => apiRequest<Version>(base + "/version"),
  checkVersion: () => post<Version>("/version/check"),
};
