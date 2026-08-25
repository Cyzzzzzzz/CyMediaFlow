import { apiRequest } from "../../api/client";
import type { LocalScrapeInfo, MediaBinding, MediaItem, MetadataCandidate, NamingPreview, NfoGenerationResult, NfoPreview, ProviderEpisode } from "../../api/types";

export type LibrarySort = "added_desc" | "name_asc";

export const libraryApi = {
  list: (search = "", sort: LibrarySort = "added_desc") => {
    const params = new URLSearchParams({ include_suggestions: "true", q: search, sort });
    return apiRequest<MediaItem[]>(`/api/v1/media?${params.toString()}`);
  },
  candidates: (id: string, query: string, provider: "bangumi" | "tmdb") => apiRequest<MetadataCandidate[]>(`/api/v1/media/${id}/metadata/search`, { method: "POST", body: JSON.stringify({ query, provider }) }),
  metadataDetail: (id: string, externalId: string, provider: "bangumi" | "tmdb") => apiRequest<MetadataCandidate>(`/api/v1/media/${id}/metadata/detail`, { method: "POST", body: JSON.stringify({ external_id: externalId, provider }) }),
  metadataEpisodes: (id: string, externalId: string, provider: "bangumi" | "tmdb", seasonNumber: number) => apiRequest<ProviderEpisode[]>(`/api/v1/media/${id}/metadata/episodes`, { method: "POST", body: JSON.stringify({ external_id: externalId, provider, season_number: seasonNumber }) }),
  scrapeInfo: (id: string) => apiRequest<LocalScrapeInfo>(`/api/v1/media/${id}/scrape-info`),
  binding: async (id: string) => (await apiRequest<MediaItem>(`/api/v1/media/${id}`)).binding,
  saveBinding: (id: string, binding: MediaBinding) => apiRequest<MediaBinding>(`/api/v1/media/${id}/scrape-config`, { method: "PUT", body: JSON.stringify(binding) }),
  namingPreview: (id: string, binding: MediaBinding) => apiRequest<NamingPreview>(`/api/v1/media/${id}/naming-preview`, {
    method: "POST",
    body: JSON.stringify({
      preferred_title: binding.preferred_title,
      season_number: binding.season_number,
      episode_offset: binding.episode_offset,
      filename_template: binding.filename_template,
      bangumi_id: binding.bangumi_id,
      bangumi_episode_count: typeof binding.metadata.bangumi_episode_count === "number" ? binding.metadata.bangumi_episode_count : null,
    }),
  }),
  nfoPreview: (id: string, binding: MediaBinding) => {
    const provider = binding.metadata.primary_provider === "tmdb" ? "tmdb" : "bangumi";
    const episodeCount = binding.metadata[`${provider}_episode_count`];
    return apiRequest<NfoPreview>(`/api/v1/media/${id}/nfo-preview`, {
      method: "POST",
      body: JSON.stringify({
        season_number: binding.season_number,
        episode_offset: binding.episode_offset,
        episode_mapping_mode: episodeMappingMode(binding),
        local_episode_number: metadataInteger(binding, "nfo_local_episode_number", 1),
        provider_episode_number: metadataInteger(binding, "nfo_provider_episode_number", 1),
        local_episode_offset: metadataInteger(binding, "nfo_local_episode_offset", 0),
        overwrite_existing: true,
        bangumi_id: provider === "tmdb" ? binding.tmdb_id : binding.bangumi_id,
        bangumi_episode_count: typeof episodeCount === "number" ? episodeCount : null,
      }),
    });
  },
  generateNfo: (id: string, binding: MediaBinding, provider: "bangumi" | "tmdb", fallbackId?: string | null) => apiRequest<NfoGenerationResult>(`/api/v1/media/${id}/nfo-generate`, {
    method: "POST",
    body: JSON.stringify({
      confirmed: true,
      provider,
      bangumi_id: binding.bangumi_id || (provider === "bangumi" ? fallbackId : null),
      tmdb_id: binding.tmdb_id || (provider === "tmdb" ? fallbackId : null),
      season_number: binding.season_number,
      episode_offset: binding.episode_offset,
      episode_mapping_mode: episodeMappingMode(binding),
      local_episode_number: metadataInteger(binding, "nfo_local_episode_number", 1),
      provider_episode_number: metadataInteger(binding, "nfo_provider_episode_number", 1),
      local_episode_offset: metadataInteger(binding, "nfo_local_episode_offset", 0),
      excluded_paths: stringList(binding.metadata.nfo_excluded_paths),
      included_paths: stringList(binding.metadata.nfo_included_paths),
      overwrite_existing: true,
      locked_fields: stringList(binding.metadata.nfo_locked_fields),
      manual_values: objectRecord(binding.metadata.nfo_manual_values),
    }),
  }),
};

function stringList(value: unknown): string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : [];
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function episodeMappingMode(binding: MediaBinding): "auto" | "manual" | "single" {
  const value = binding.metadata.nfo_episode_mapping_mode;
  return value === "manual" || value === "single" ? value : "auto";
}

function metadataInteger(binding: MediaBinding, key: string, fallback: number): number {
  const value = binding.metadata[key];
  return typeof value === "number" && Number.isInteger(value) ? value : fallback;
}
