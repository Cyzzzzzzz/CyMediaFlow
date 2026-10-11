import { apiRequest } from "../../api/client";
import type { Download, Event, Feed, FeedAnalysis, Release, ReleaseAnalysis, Subscription, SubscriptionDraft, SubscriptionMatch } from "./types";

export const automationApi = {
  analyze: (value: { url: string; parser: "bangumi" | "tmdb" | "parser" }) => apiRequest<FeedAnalysis>("/api/v1/automation/feeds/analyze", { method: "POST", body: JSON.stringify(value) }),
  subscribe: (value: { url: string; name: string; rules: SubscriptionDraft[] }) => apiRequest<{ created: number; automation_enabled: boolean }>("/api/v1/automation/subscriptions/confirm", { method: "POST", body: JSON.stringify(value) }),
  searchMetadata: (provider: "bangumi" | "tmdb", query: string) => apiRequest<SubscriptionMatch[]>("/api/v1/automation/metadata/search", { method: "POST", body: JSON.stringify({ provider, query }) }),
  feeds: () => apiRequest<Feed[]>("/api/v1/automation/feeds"),
  saveFeed: (id: number | null, value: { name: string; url: string | null; enabled: boolean }) => apiRequest<Feed>(id ? `/api/v1/automation/feeds/${id}` : "/api/v1/automation/feeds", { method: id ? "PUT" : "POST", body: JSON.stringify(value) }),
  deleteFeed: (id: number) => apiRequest<{ deleted: boolean }>(`/api/v1/automation/feeds/${id}`, { method: "DELETE" }),
  previewFeed: (id: number) => apiRequest<{ title: string; analysis: ReleaseAnalysis }[]>(`/api/v1/automation/feeds/${id}/preview`, { method: "POST" }),
  refreshFeed: (id: number) => apiRequest<{ fetched: number; submitted: number }>(`/api/v1/automation/feeds/${id}/refresh`, { method: "POST" }),
  rules: () => apiRequest<Subscription[]>("/api/v1/automation/subscriptions"),
  saveRule: (id: number | null, value: Omit<Subscription, "id">) => apiRequest<Subscription>(id ? `/api/v1/automation/subscriptions/${id}` : "/api/v1/automation/subscriptions", { method: id ? "PUT" : "POST", body: JSON.stringify(value) }),
  deleteRule: (id: number) => apiRequest<{ deleted: boolean }>(`/api/v1/automation/subscriptions/${id}`, { method: "DELETE" }),
  releases: () => apiRequest<Release[]>("/api/v1/automation/releases"),
  downloads: () => apiRequest<Download[]>("/api/v1/automation/downloads"),
  syncDownloads: () => apiRequest<{ synced: boolean }>("/api/v1/automation/downloads/sync", { method: "POST" }),
  events: () => apiRequest<Event[]>("/api/v1/automation/events"),
  run: () => apiRequest<{ status: string }>("/api/v1/automation/run", { method: "POST" }),
};
