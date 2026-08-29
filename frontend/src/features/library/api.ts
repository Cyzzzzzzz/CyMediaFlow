import { apiRequest } from "../../api/client";
import type { CachedMetadataSearch, EpisodeMappingSuggestion, LocalScrapeInfo, MediaBinding, MediaItem, MetadataCandidate, NamingPreview, NfoGenerationResult, NfoPreview, ProviderEpisode, ProviderSubjectBinding, ScheduledRefresh, SeasonArtworkExtractionResult } from "../../api/types";

export type LibrarySort = "added_desc" | "name_asc";

export const libraryApi = {
  list: (search = "", sort: LibrarySort = "added_desc") => {
    const params = new URLSearchParams({ include_suggestions: "true", q: search, sort });
    return apiRequest<MediaItem[]>(`/api/v1/media?${params.toString()}`);
  },
  candidates: (id: string, query: string, provider: "bangumi" | "tmdb", limit = 10, refresh = false) => apiRequest<MetadataCandidate[]>(`/api/v1/media/${id}/metadata/search`, { method: "POST", body: JSON.stringify({ query, provider, limit, refresh }) }),
  cachedCandidates: (id: string, provider: "bangumi" | "tmdb") => apiRequest<CachedMetadataSearch | null>(`/api/v1/media/${id}/metadata/search-cache?provider=${provider}`),
  metadataDetail: (id: string, externalId: string, provider: "bangumi" | "tmdb", refresh = false) => apiRequest<MetadataCandidate>(`/api/v1/media/${id}/metadata/detail`, { method: "POST", body: JSON.stringify({ external_id: externalId, provider, refresh }) }),
  metadataEpisodes: (id: string, externalId: string, provider: "bangumi" | "tmdb", seasonNumber: number, refresh = false) => apiRequest<ProviderEpisode[]>(`/api/v1/media/${id}/metadata/episodes`, { method: "POST", body: JSON.stringify({ external_id: externalId, provider, season_number: seasonNumber, refresh }) }),
  suggestEpisodeMapping: (id: string, providerSubjects: ProviderSubjectBinding[], defaultSeason: number) => apiRequest<EpisodeMappingSuggestion>(`/api/v1/media/${id}/episode-mapping/suggest`, {
    method: "POST",
    body: JSON.stringify({ provider_subjects: providerSubjects, default_season: defaultSeason }),
  }),
  scrapeInfo: (id: string, refresh = false) => apiRequest<LocalScrapeInfo>(`/api/v1/media/${id}/scrape-info?refresh=${refresh}`),
  extractSeasonArtwork: (id: string, seasonNumber: number) => apiRequest<SeasonArtworkExtractionResult>(`/api/v1/media/${id}/artwork/seasons/${seasonNumber}/extract`, { method: "POST" }),
  binding: async (id: string) => (await apiRequest<MediaItem>(`/api/v1/media/${id}`)).binding,
  saveBinding: (id: string, binding: MediaBinding) => apiRequest<MediaBinding>(`/api/v1/media/${id}/scrape-config`, { method: "PUT", body: JSON.stringify(binding) }),
  runScheduledRefresh: (id: string) => apiRequest<ScheduledRefresh>(`/api/v1/media/${id}/scheduled-refresh/run`, { method: "POST" }),
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
  nfoPreview: (id: string, binding: MediaBinding, refresh = false) => {
    const primary = primarySource(binding);
    const provider = primary.provider;
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
        bangumi_id: primary.externalId,
        bangumi_episode_count: typeof episodeCount === "number" ? episodeCount : null,
        episode_source_rules: binding.episode_source_rules,
        excluded_folders: stringList(binding.metadata.nfo_excluded_folders),
        refresh,
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
      excluded_folders: stringList(binding.metadata.nfo_excluded_folders),
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

function episodeMappingMode(binding: MediaBinding): "auto" | "manual" | "single" | "segments" {
  const value = binding.metadata.nfo_episode_mapping_mode;
  return value === "manual" || value === "single" || value === "segments" ? value : "auto";
}

function metadataInteger(binding: MediaBinding, key: string, fallback: number): number {
  const value = binding.metadata[key];
  return typeof value === "number" && Number.isInteger(value) ? value : fallback;
}

function primarySource(binding: MediaBinding): { provider: "bangumi" | "tmdb"; externalId: string | null } {
  const explicit = binding.provider_subjects.find((subject) => subject.role === "primary");
  if (explicit) return { provider: explicit.provider, externalId: explicit.external_id };
  if (binding.metadata.primary_provider === "tmdb" && binding.tmdb_id) {
    return { provider: "tmdb", externalId: binding.tmdb_id };
  }
  if (binding.metadata.primary_provider === "bangumi" && binding.bangumi_id) {
    return { provider: "bangumi", externalId: binding.bangumi_id };
  }
  const first = binding.provider_subjects[0];
  if (first) return { provider: first.provider, externalId: first.external_id };
  return binding.bangumi_id || !binding.tmdb_id
    ? { provider: "bangumi", externalId: binding.bangumi_id }
    : { provider: "tmdb", externalId: binding.tmdb_id };
}
