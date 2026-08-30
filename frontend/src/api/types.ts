export type ExternalIdentity = { provider: string; external_id: string };
export type MediaItem = {
  id: string; folder_name: string; title: string; year: number | null; path: string; added_at: string; poster_url: string | null;
  video_count: number; seasons: number[]; nfo_present: boolean; external_ids: ExternalIdentity[];
  status: "matched" | "configured" | "unconfigured"; binding: MediaBinding | null;
};
export type ProviderInfoboxValue = { value: string; label: string | null };
export type ProviderInfoboxItem = { key: string; values: ProviderInfoboxValue[] };
export type ProviderPerson = {
  external_id: string; name: string; relation: string | null; career: string[];
  episode_scope: string | null; image_url: string | null;
};
export type ProviderCharacter = {
  external_id: string; name: string; relation: string; summary: string | null;
  image_url: string | null; actors: ProviderPerson[]; infobox: ProviderInfoboxItem[];
  birth_year: number | null; birth_month: number | null; birth_day: number | null;
  gender: string | null; blood_type: string | null;
};
export type ProviderRelatedSubject = {
  external_id: string; name: string; title: string | null; relation: string;
  subject_type: number | null; image_url: string | null;
};
export type ProviderRating = {
  score: number | null; rank: number | null; total: number; distribution: [number, number][];
};
export type ProviderTag = { name: string; count: number; total_count: number };
export type MetadataCandidate = {
  provider: "bangumi" | "tmdb"; external_id: string; title: string; original_title: string | null;
  year: number | null; episode_count: number | null; image_url: string | null; summary: string | null;
  premiere_date?: string | null; platform?: string | null; total_episode_count?: number | null;
  infobox?: ProviderInfoboxItem[]; rating?: ProviderRating | null; meta_tags?: string[];
  tags?: ProviderTag[]; persons?: ProviderPerson[]; characters?: ProviderCharacter[];
  related_subjects?: ProviderRelatedSubject[];
};
export type CachedMetadataSearch = {
  query: string; limit: number; candidates: MetadataCandidate[];
};
export type ProviderEpisode = {
  provider: "bangumi" | "tmdb"; external_id: string; episode_number: number;
  title: string; original_title: string | null; air_date: string | null;
  summary: string | null; runtime_minutes: number | null; image_url: string | null;
  episode_type?: number; sort_number?: number | null;
};
export type ProviderSubjectRole = "primary" | "season" | "season_part" | "movie" | "special" | "related" | "metadata_only";
export type ProviderSubjectBinding = {
  provider: "bangumi" | "tmdb"; external_id: string; title: string;
  original_title: string | null; image_url: string | null; role: ProviderSubjectRole;
};
export type EpisodeSourceRule = {
  provider: "bangumi" | "tmdb"; external_id: string; local_season: number;
  local_episode_start: number; local_episode_end: number | null; provider_episode_start: number;
  provider_season: number; number_mode: "episode" | "sort"; local_path?: string | null;
};
export type DetectedEpisodeRange = {
  season_number: number; episode_start: number; episode_end: number; episode_count: number;
};
export type DetectedSingleFile = {
  relative_path: string; video_name: string; suggested_season: number; suggested_episode: number;
};
export type EpisodeMappingSuggestion = {
  rules: EpisodeSourceRule[]; detected_ranges: DetectedEpisodeRange[];
  detected_single_files: DetectedSingleFile[]; warnings: string[];
};
export type ScheduledRefresh = {
  enabled: boolean; daily_time: string; last_run_at: string | null;
  last_status: "never" | "success" | "failed" | "completed";
  last_message: string | null; current_episode: number | null;
  total_episodes: number | null; final_air_date: string | null;
};
export type MediaBinding = {
  bangumi_id: string | null; tmdb_id: string | null; preferred_title: string | null; content_kind: string;
  year: number | null; season_number: number; episode_offset: number; folder_template: string; filename_template: string;
  emby_enabled: boolean; image_url: string | null; metadata: Record<string, unknown>;
  provider_subjects: ProviderSubjectBinding[]; episode_source_rules: EpisodeSourceRule[];
  scheduled_refresh: ScheduledRefresh;
};
export type SettingsView = {
  media_root: string; allowed_media_root: string; allowed_media_roots: string[]; media_root_exists: boolean; media_root_readable: boolean;
  bangumi_configured: boolean; bangumi_api_url: string; tmdb_configured: boolean; tmdb_api_url: string;
  operation_mode: "nfo_create_only" | "nfo_managed_update";
  bangumi_proxy_enabled: boolean; bangumi_proxy_url: string | null;
  tmdb_proxy_enabled: boolean; tmdb_proxy_url: string | null;
  episode_artwork_fallback_enabled: boolean; episode_artwork_capture_percent: number;
  ffprobe_path: string; ffprobe_available: boolean;
  ffmpeg_path: string; ffmpeg_available: boolean;
  ignore_marker_enabled: boolean; ignore_folder_patterns: string[];
  ignore_marker_matched_count: number; ignore_marker_created_count: number;
  ignore_marker_existing_count: number; ignore_marker_failed_count: number;
};
export type SettingsUpdate = {
  media_root: string; bangumi_access_token: string | null; clear_bangumi_access_token: boolean;
  bangumi_proxy_enabled: boolean; bangumi_proxy_url: string | null;
  tmdb_access_token: string | null; clear_tmdb_access_token: boolean;
  tmdb_proxy_enabled: boolean; tmdb_proxy_url: string | null;
  operation_mode: "nfo_create_only" | "nfo_managed_update";
  episode_artwork_fallback_enabled: boolean; episode_artwork_capture_percent: number;
  ffprobe_path: string; ffmpeg_path: string;
  ignore_marker_enabled: boolean; ignore_folder_patterns: string[];
};
export type ParseTraceStep = { stage: string; value: string; detail: string };
export type ParsedMediaInfo = {
  raw_filename: string; stem: string; extension: string; file_role: "video" | "subtitle" | "other";
  title: string | null; title_candidates: string[]; year: number | null; season: number | null;
  episode_start: number | null; episode_end: number | null; absolute_episode_start: number | null;
  absolute_episode_end: number | null; special_type: string | null; special_number: number | null;
  release_group: string | null; resolution: string | null; source: string | null;
  video_codec: string | null; audio_codec: string | null; bit_depth: number | null; version: number | null;
  subtitle_language: string | null; subtitle_flags: string[]; matched_rule_id: string | null;
  confidence: number; warnings: string[]; trace: ParseTraceStep[];
};
export type NamingPreviewEntry = {
  source_relative_path: string; target_relative_path: string; source_name: string; target_name: string;
  status: "rename" | "unchanged" | "review" | "conflict"; folder: string; category: string;
  default_selected: boolean; selection_reason: string | null; parsed: ParsedMediaInfo; warnings: string[];
};
export type NamingPreview = {
  media_id: string; operation_mode: "read_only_preview"; total: number; rename_count: number;
  unchanged_count: number; review_count: number; conflict_count: number; default_selected_count: number;
  default_skipped_count: number; entries: NamingPreviewEntry[];
};
export type NfoPreviewEntry = {
  video_relative_path: string; video_name: string; source_nfo_relative_path: string | null;
  source_nfo_name: string | null; target_nfo_relative_path: string; target_nfo_name: string;
  action: "create" | "rename" | "unchanged" | "review" | "conflict"; folder: string;
  category: string; default_selected: boolean; selection_reason: string | null;
  parsed: ParsedMediaInfo; warnings: string[];
};
export type NfoPreview = {
  media_id: string; operation_mode: "read_only_preview"; total: number; create_count: number;
  rename_count: number; unchanged_count: number; review_count: number; conflict_count: number;
  default_selected_count: number; default_skipped_count: number; entries: NfoPreviewEntry[];
};
export type NfoGenerationResult = {
  media_id: string; bangumi_id: string; provider: "bangumi" | "tmdb"; external_id: string | null; created_files: string[];
  updated_files: string[]; locked_fields: string[];
  created_artwork_files: string[];
  artwork_warnings: { relative_path: string; reason: string }[];
  skipped_files: { relative_path: string; reason: string }[]; generated_episode_count: number;
  probe_warnings: { relative_path: string; reason: string }[];
};
export type SubtitleMatchEntry = {
  source_relative_path: string; source_name: string; target_relative_path: string | null;
  target_name: string | null; video_relative_path: string | null; video_name: string | null;
  folder: string; season_number: number | null; episode_number: number | null;
  language: string | null; language_tag: string | null;
  status: "rename" | "unchanged" | "review" | "conflict"; default_selected: boolean;
  reason: string | null; warnings: string[];
};
export type SubtitleMatchPreview = {
  media_id: string; operation_mode: "read_only_preview"; total: number; rename_count: number;
  unchanged_count: number; review_count: number; conflict_count: number;
  default_selected_count: number; entries: SubtitleMatchEntry[];
};
export type SubtitleRenameResult = {
  media_id: string;
  renamed_files: { source_relative_path: string; target_relative_path: string }[];
  skipped_files: { relative_path: string; reason: string }[];
};
export type SeasonArtworkExtractionResult = {
  media_id: string; season_number: number; target_count: number; created_files: string[];
  skipped_files: { relative_path: string; reason: string }[];
  failed_files: { relative_path: string; reason: string }[];
};
export type SeriesScrapeInfo = {
  title: string; original_title: string | null; plot: string | null; year: number | null;
  premiered: string | null; end_date: string | null; status: string | null; rating: number | null;
  runtime: number | null; genres: string[]; tags: string[]; studios: string[]; cast: string[];
  directors: string[]; writers: string[]; external_ids: ExternalIdentity[];
  artwork: string[]; provider_data: string | null;
  poster_url: string | null; poster_source: string;
};
export type EpisodeScrapeInfo = {
  season_number: number; episode_number: number; title: string; original_title: string | null;
  plot: string | null; aired: string | null; runtime: number | null; external_ids: ExternalIdentity[];
  artwork: string[]; provider_data: string | null; media_streams: string | null;
  nfo_relative_path: string; poster_url: string | null; poster_source: string;
};
export type SeasonScrapeInfo = {
  season_number: number; title: string | null; original_title: string | null; plot: string | null;
  year: number | null; premiered: string | null; cast: string[]; external_ids: ExternalIdentity[];
  artwork: string[]; provider_data: string | null;
  nfo_relative_path: string | null; poster_url: string | null; poster_source: string;
  episodes: EpisodeScrapeInfo[];
};
export type LocalScrapeInfo = { media_id: string; series: SeriesScrapeInfo | null; seasons: SeasonScrapeInfo[] };
