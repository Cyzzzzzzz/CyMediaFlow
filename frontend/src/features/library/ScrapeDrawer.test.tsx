import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EpisodeMappingSuggestion, MediaBinding, MediaItem, MetadataCandidate } from "../../api/types";
import { libraryApi } from "./api";
import { ScrapeDrawer } from "./ScrapeDrawer";

vi.mock("./api", () => ({
  libraryApi: {
    binding: vi.fn(),
    candidates: vi.fn(),
    cachedCandidates: vi.fn(),
    metadataDetail: vi.fn(),
    metadataEpisodes: vi.fn(),
    scrapeInfo: vi.fn(),
    saveBinding: vi.fn(),
    generateNfo: vi.fn(),
    suggestEpisodeMapping: vi.fn(),
    nfoPreview: vi.fn(),
  },
}));

const binding: MediaBinding = {
  bangumi_id: "111",
  tmdb_id: null,
  preferred_title: "分割放送番剧",
  content_kind: "series",
  year: 2026,
  season_number: 1,
  episode_offset: 0,
  folder_template: "{title} ({year})/Season {season:02}",
  filename_template: "{title} S{season:02}E{episode:02}",
  emby_enabled: true,
  image_url: null,
  metadata: { primary_provider: "bangumi", nfo_episode_mapping_mode: "segments" },
  provider_subjects: [{
    provider: "bangumi",
    external_id: "111",
    title: "分割放送番剧",
    original_title: null,
    image_url: null,
    role: "primary",
  }],
  episode_source_rules: [{
    provider: "bangumi",
    external_id: "111",
    local_season: 1,
    local_episode_start: 1,
    local_episode_end: 12,
    provider_episode_start: 1,
    provider_season: 1,
    number_mode: "sort",
  }],
};

const item: MediaItem = {
  id: "anime-1",
  folder_name: "分割放送番剧",
  title: "分割放送番剧",
  year: 2026,
  path: "/media/anime-1",
  added_at: "2026-01-01T00:00:00+00:00",
  poster_url: null,
  video_count: 12,
  seasons: [1],
  nfo_present: false,
  external_ids: [],
  status: "configured",
  binding,
};

const detail: MetadataCandidate = {
  provider: "bangumi",
  external_id: "111",
  title: "分割放送番剧",
  original_title: null,
  year: 2026,
  episode_count: 12,
  image_url: null,
  summary: null,
};

const suggestion: EpisodeMappingSuggestion = {
  detected_ranges: [{ season_number: 1, episode_start: 1, episode_end: 12, episode_count: 12 }],
  detected_single_files: [],
  rules: binding.episode_source_rules,
  warnings: [],
};

function renderDrawer() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ScrapeDrawer item={item} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("ScrapeDrawer segmented mapping", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(libraryApi.binding).mockResolvedValue(binding);
    vi.mocked(libraryApi.candidates).mockResolvedValue([]);
    vi.mocked(libraryApi.cachedCandidates).mockResolvedValue(null);
    vi.mocked(libraryApi.metadataDetail).mockResolvedValue(detail);
    vi.mocked(libraryApi.metadataEpisodes).mockResolvedValue([]);
    vi.mocked(libraryApi.scrapeInfo).mockResolvedValue({ media_id: "anime-1", series: null, seasons: [] });
    vi.mocked(libraryApi.saveBinding).mockImplementation(async (_id, value) => value);
    vi.mocked(libraryApi.generateNfo).mockResolvedValue({
      media_id: "anime-1", bangumi_id: "111", provider: "bangumi", external_id: "111",
      created_files: [], updated_files: [], locked_fields: [], created_artwork_files: [],
      artwork_warnings: [], skipped_files: [], generated_episode_count: 0, probe_warnings: [],
    });
    vi.mocked(libraryApi.suggestEpisodeMapping).mockResolvedValue(suggestion);
    vi.mocked(libraryApi.nfoPreview).mockResolvedValue({
      media_id: "anime-1", operation_mode: "read_only_preview", total: 0,
      create_count: 0, rename_count: 0, unchanged_count: 0, review_count: 0,
      conflict_count: 0, default_selected_count: 0, default_skipped_count: 0, entries: [],
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("does not search on open and refreshes expensive data only from its buttons", async () => {
    renderDrawer();
    await screen.findByText("主作品");

    expect(libraryApi.candidates).not.toHaveBeenCalled();
    expect(libraryApi.metadataDetail).not.toHaveBeenCalled();
    expect(await screen.findByText(/尚无搜索缓存/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    await waitFor(() => expect(libraryApi.candidates).toHaveBeenCalledWith(
      "anime-1", "分割放送番剧", "bangumi", 10, true,
    ));

    fireEvent.click(screen.getByText("刮削信息"));
    expect(await screen.findByRole("button", { name: "刮削元数据" })).toBeTruthy();
    await waitFor(() => expect(libraryApi.metadataDetail).toHaveBeenCalledWith(
      "anime-1", "111", "bangumi", false,
    ));
    fireEvent.click(screen.getByRole("button", { name: "刮削元数据" }));
    await waitFor(() => {
      expect(libraryApi.metadataDetail).toHaveBeenCalledWith(
        "anime-1", "111", "bangumi", true,
      );
      expect(libraryApi.metadataEpisodes).toHaveBeenCalledWith(
        "anime-1", "111", "bangumi", 1, true,
      );
      expect(libraryApi.scrapeInfo).toHaveBeenCalledWith("anime-1", true);
    });

    fireEvent.click(screen.getByText("NFO 文件"));
    expect(await screen.findByRole("button", { name: "更新预览" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "更新预览" }));
    await waitFor(() => expect(libraryApi.nfoPreview).toHaveBeenCalledWith(
      "anime-1", expect.any(Object), true,
    ));
  });

  it("restores the last candidate list without performing another provider search", async () => {
    vi.mocked(libraryApi.cachedCandidates).mockResolvedValue({
      query: "上次搜索词",
      limit: 10,
      candidates: [{ ...detail, external_id: "222", title: "缓存候选作品" }],
    });

    renderDrawer();

    expect(await screen.findByText("缓存候选作品")).toBeTruthy();
    expect(screen.getByText(/上一次搜索“上次搜索词”/)).toBeTruthy();
    expect((screen.getByLabelText("搜索 bangumi") as HTMLInputElement).value).toBe("上次搜索词");
    expect(libraryApi.candidates).not.toHaveBeenCalled();
  });

  it("shows the drawer sections in the requested workflow order", async () => {
    renderDrawer();
    await screen.findByText("主作品");

    const sectionTitles = Array.from(document.querySelectorAll(".accordion-trigger strong"))
      .map((element) => element.textContent);
    expect(sectionTitles.slice(0, 4)).toEqual([
      "作品匹配",
      "NFO 文件",
      "季集映射",
      "刮削信息",
    ]);
  });

  it("hides legacy offsets, labels providers, and applies a reviewable suggestion", async () => {
    renderDrawer();
    await screen.findByText("主作品");
    fireEvent.click(screen.getByText("季集映射"));

    expect(await screen.findByLabelText("本地季（Emby）")).toBeTruthy();
    expect(screen.queryByLabelText("Emby 季号")).toBeNull();
    expect(screen.queryByLabelText("集数偏移")).toBeNull();
    expect(screen.getByLabelText("Bangumi 编号字段")).toBeTruthy();
    expect(screen.queryByLabelText("TMDB 远程季")).toBeNull();
    expect(screen.getAllByText("Bangumi").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "智能生成" }));
    await waitFor(() => expect(libraryApi.suggestEpisodeMapping).toHaveBeenCalledWith(
      "anime-1",
      binding.provider_subjects,
      1,
    ));
    expect(await screen.findByText(/已识别 S01 E01–E12，生成 1 条规则/)).toBeTruthy();
  });

  it("shows an editable file mapping for a detected nested movie main video", async () => {
    const movieSubject = {
      provider: "bangumi" as const,
      external_id: "152092",
      title: "剧场版 吹响吧！上低音号",
      original_title: null,
      image_url: null,
      role: "movie" as const,
    };
    const moviePath = "Sound Euphonium The Movie/[Main] Sound Euphonium The Movie.mkv";
    vi.mocked(libraryApi.binding).mockResolvedValue({
      ...binding,
      provider_subjects: [...binding.provider_subjects, movieSubject],
    });
    vi.mocked(libraryApi.suggestEpisodeMapping).mockResolvedValue({
      detected_ranges: suggestion.detected_ranges,
      detected_single_files: [{
        relative_path: moviePath,
        video_name: "[Main] Sound Euphonium The Movie.mkv",
        suggested_season: 0,
        suggested_episode: 1,
      }],
      warnings: [],
      rules: [...binding.episode_source_rules, {
        provider: "bangumi",
        external_id: "152092",
        local_season: 0,
        local_episode_start: 1,
        local_episode_end: 1,
        provider_episode_start: 1,
        provider_season: 1,
        number_mode: "sort",
        local_path: moviePath,
      }],
    });

    renderDrawer();
    await screen.findByText("主作品");
    fireEvent.click(screen.getByText("季集映射"));
    fireEvent.click(screen.getByRole("button", { name: "智能生成" }));

    expect(await screen.findByDisplayValue(moviePath)).toBeTruthy();
    expect(screen.getByText(/\[Main\] Sound Euphonium The Movie\.mkv → S00E01/)).toBeTruthy();
    expect(screen.getByLabelText("本地集（Emby）")).toBeTruthy();
  });

  it("repairs a stale TMDB default and generates from the available Bangumi main work", async () => {
    const staleBinding: MediaBinding = {
      ...binding,
      bangumi_id: null,
      tmdb_id: null,
      metadata: { ...binding.metadata, primary_provider: "tmdb" },
      provider_subjects: binding.provider_subjects.map((subject) => ({ ...subject, role: "season_part" })),
    };
    vi.mocked(libraryApi.binding).mockResolvedValue(staleBinding);
    vi.mocked(libraryApi.saveBinding).mockImplementation(async (_id, value) => ({
      ...value,
      bangumi_id: "111",
      metadata: { ...value.metadata, primary_provider: "bangumi" },
      provider_subjects: value.provider_subjects.map((subject) => ({ ...subject, role: "primary" })),
    }));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <ScrapeDrawer item={{ ...item, binding: staleBinding }} onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    expect((await screen.findByRole("combobox", { name: "选择主作品" }) as HTMLSelectElement).value).toBe("bangumi:111");
    fireEvent.click(screen.getByText("刮削信息"));
    expect(await screen.findByText("Bangumi 主作品自动补全")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "生成 NFO" }));
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));

    await waitFor(() => expect(libraryApi.generateNfo).toHaveBeenCalled());
    expect(vi.mocked(libraryApi.generateNfo).mock.calls[0]?.[2]).toBe("bangumi");
    expect(vi.mocked(libraryApi.generateNfo).mock.calls[0]?.[3]).toBe("111");
  });
});
