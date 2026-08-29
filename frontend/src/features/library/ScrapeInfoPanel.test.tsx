import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { LocalScrapeInfo } from "../../api/types";
import { ScrapeInfoPanel } from "./ScrapeInfoPanel";

const localInfo: LocalScrapeInfo = {
  media_id: "anime-1",
  series: {
    title: "家里蹲吸血姬的苦闷", original_title: "ひきこまり吸血姫の悶々", plot: "作品简介",
    year: 2023, premiered: "2023-10-07", end_date: null, status: "Ended", rating: 5.7,
    runtime: 24, genres: ["Anime"], tags: ["奇幻"], studios: ["Project No.9"], cast: ["楠木ともり"],
    directors: ["南川達馬"], writers: ["大知慶一郎"], external_ids: [{ provider: "bangumi", external_id: "414214" }],
    artwork: [], provider_data: null,
    poster_url: "/api/v1/media/anime-1/artwork/series", poster_source: "local",
  },
  seasons: [{
    season_number: 1, title: "家里蹲吸血姬的苦闷", original_title: null, plot: "季度简介", year: 2023,
    premiered: "2023-10-07", cast: [], external_ids: [], artwork: [], provider_data: null, nfo_relative_path: "Season 1/season.nfo",
    poster_url: "/api/v1/media/anime-1/artwork/seasons/1", poster_source: "series_fallback",
    episodes: [{
      season_number: 1, episode_number: 1, title: "家里蹲吸血鬼出门去", original_title: null,
      plot: "单集简介", aired: "2023-10-07", runtime: 24, external_ids: [],
      artwork: [], provider_data: null, media_streams: null,
      nfo_relative_path: "Season 1/E01.nfo", poster_url: "/api/v1/media/anime-1/artwork/seasons/1/episodes/1",
      poster_source: "local",
    }],
  }],
};

describe("ScrapeInfoPanel", () => {
  it("shows separate series, season, and episode metadata with artwork", () => {
    const onScrapeMetadata = vi.fn();
    render(<ScrapeInfoPanel localInfo={localInfo} providerInfo={undefined} loading={false} error={false} canScrapeMetadata onScrapeMetadata={onScrapeMetadata} />);

    expect(screen.getByText("家里蹲吸血姬的苦闷")).toBeTruthy();
    expect(screen.getByRole("img", { name: "家里蹲吸血姬的苦闷 剧集海报" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "第 1 季海报" })).toBeTruthy();
    expect(screen.getByText("沿用剧集海报")).toBeTruthy();
    expect(screen.getByRole("img", { name: "第 1 集海报" })).toBeTruthy();
    expect(screen.getByText("家里蹲吸血鬼出门去")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "刮削元数据" }));
    expect(onScrapeMetadata).toHaveBeenCalledOnce();
  });

  it("always shows the complete Bangumi entry while details are not loaded", () => {
    render(<ScrapeInfoPanel
      provider="bangumi"
      localInfo={localInfo}
      providerInfo={undefined}
      loading={false}
      error={false}
    />);

    expect(screen.getByText("Bangumi 完整条目信息")).toBeTruthy();
    expect(screen.getByText("尚未配置 Bangumi 季度条目")).toBeTruthy();
    fireEvent.click(screen.getByText("Bangumi 完整条目信息"));
    expect(screen.getByText(/请先将 Bangumi 条目设为主作品/)).toBeTruthy();
  });

  it("requires an explicit confirmation before generating missing NFO files", () => {
    const onGenerate = vi.fn();
    render(<ScrapeInfoPanel
      localInfo={{ media_id: "anime-1", series: null, seasons: [] }}
      providerInfo={{
        provider: "bangumi", external_id: "414214", title: "家里蹲吸血姬的苦闷",
        original_title: "ひきこまり吸血姫の悶々", year: 2023, episode_count: 12,
        image_url: null, summary: "作品简介",
      }}
      loading={false}
      error={false}
      onGenerate={onGenerate}
    />);

    fireEvent.click(screen.getByRole("button", { name: "生成 NFO" }));
    expect(onGenerate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));
    expect(onGenerate).toHaveBeenCalledOnce();
  });

  it("lets the user edit and lock an NFO field before an update", () => {
    const onFieldPolicyChange = vi.fn();
    render(<ScrapeInfoPanel
      localInfo={localInfo}
      providerInfo={undefined}
      loading={false}
      error={false}
      onFieldPolicyChange={onFieldPolicyChange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "编辑与锁定" }));
    fireEvent.change(screen.getByRole("textbox", { name: "剧集标题" }), {
      target: { value: "我的自定义标题" },
    });

    expect(onFieldPolicyChange).toHaveBeenCalledWith(
      ["series.title"],
      { "series.title": "我的自定义标题" },
    );
  });

  it("stores an edited episode title under its season and episode scope", () => {
    const onFieldPolicyChange = vi.fn();
    render(<ScrapeInfoPanel
      localInfo={localInfo}
      providerInfo={undefined}
      loading={false}
      error={false}
      onFieldPolicyChange={onFieldPolicyChange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "编辑与锁定" }));
    fireEvent.change(screen.getByRole("textbox", { name: "分集标题" }), {
      target: { value: "手工第一集" },
    });

    expect(onFieldPolicyChange).toHaveBeenCalledWith(
      ["episodes.title@1:1"],
      { "episodes.title": { "1:1": "手工第一集" } },
    );
  });

  it("uses the selected TMDB provider in scrape and NFO status text", () => {
    render(<ScrapeInfoPanel
      provider="tmdb"
      localInfo={localInfo}
      providerInfo={{
        provider: "tmdb", external_id: "96316", title: "租借女友",
        original_title: "彼女、お借りします", year: 2020, episode_count: 60,
        image_url: null, summary: "作品简介",
      }}
      loading={false}
      error={false}
      canScrapeMetadata
      scrapeMetadataSuccess
    />);

    expect(screen.getByText("TMDB 元数据")).toBeTruthy();
    expect(screen.getByText("已读取最新 TMDB 元数据，尚未写入 NFO")).toBeTruthy();
    expect(screen.getByText("TMDB 主作品自动补全")).toBeTruthy();
    expect(screen.queryByText("已读取最新 Bangumi 元数据，尚未写入 NFO")).toBeNull();
  });

  it("expands remote episode scrape data and collapses it on the second click", () => {
    render(<ScrapeInfoPanel
      provider="tmdb"
      localInfo={localInfo}
      providerInfo={undefined}
      providerEpisodes={[{
        provider: "tmdb", external_id: "9001", episode_number: 1,
        title: "远程第一集", original_title: "Remote Episode One",
        air_date: "2023-10-07", summary: "TMDB 分集简介", runtime_minutes: 24,
        image_url: "https://image.tmdb.org/t/p/w780/still.jpg",
      }]}
      loading={false}
      error={false}
    />);

    const episode = screen.getByRole("button", { name: /远程第一集/ });
    expect(screen.queryByText("TMDB 分集刮削数据")).toBeNull();
    fireEvent.click(episode);
    expect(screen.getByText("TMDB 分集刮削数据")).toBeTruthy();
    expect(screen.getByText("TMDB 分集简介")).toBeTruthy();
    expect(screen.getByRole("img", { name: "第 1 集刮削图片" })).toBeTruthy();
    fireEvent.click(episode);
    expect(screen.queryByText("TMDB 分集刮削数据")).toBeNull();
  });

  it("does not overwrite another local season with the currently browsed subject", () => {
    const segmentedInfo: LocalScrapeInfo = {
      ...localInfo,
      seasons: [
        {
          ...localInfo.seasons[0],
          episodes: [{
            ...localInfo.seasons[0].episodes[0],
            title: "本地第一季第一集",
            external_ids: [{ provider: "bangumi", external_id: "episode-s1-1" }],
          }],
        },
        {
          ...localInfo.seasons[0],
          season_number: 2,
          title: "本地第二季",
          nfo_relative_path: "Season 2/season.nfo",
          episodes: [{
            ...localInfo.seasons[0].episodes[0],
            season_number: 2,
            title: "本地第二季第一集",
            external_ids: [{ provider: "bangumi", external_id: "episode-s2-1" }],
            nfo_relative_path: "Season 2/E01.nfo",
          }],
        },
      ],
    };
    render(<ScrapeInfoPanel
      provider="bangumi"
      localInfo={segmentedInfo}
      providerInfo={undefined}
      providerEpisodes={[{
        provider: "bangumi", external_id: "episode-s1-1", episode_number: 1,
        title: "远程第一季第一集", original_title: null,
        air_date: null, summary: "第一季远程简介", runtime_minutes: 24,
        image_url: null,
      }]}
      seasonNumber={1}
      loading={false}
      error={false}
    />);

    expect(screen.getByText("远程第一季第一集")).toBeTruthy();
    expect(screen.getByText("本地第二季第一集")).toBeTruthy();
    expect(screen.queryByText("本地第一季第一集")).toBeNull();
  });

  it("batch locks each series, season, and episode field group independently", () => {
    const onFieldPolicyChange = vi.fn();
    render(<ScrapeInfoPanel
      localInfo={localInfo}
      providerInfo={undefined}
      loading={false}
      error={false}
      onFieldPolicyChange={onFieldPolicyChange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "编辑与锁定" }));
    fireEvent.click(screen.getByRole("button", { name: "锁定全部剧集字段" }));
    let [locks, values] = onFieldPolicyChange.mock.calls.at(-1)!;
    expect(locks).toEqual(["series.*"]);
    expect(Object.keys(values)).toHaveLength(15);

    fireEvent.click(screen.getByRole("button", { name: "锁定第 1 季季度字段" }));
    [locks, values] = onFieldPolicyChange.mock.calls.at(-1)!;
    expect(locks).toEqual(["season.*@1"]);
    expect(Object.values(values).every((value) => typeof value === "object")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "锁定S01E01 全部字段" }));
    [locks] = onFieldPolicyChange.mock.calls.at(-1)!;
    expect(locks).toEqual(["episodes.*@1:1"]);
  });

  it("batch unlocks a protected field group and clears its saved values", () => {
    const onFieldPolicyChange = vi.fn();
    render(<ScrapeInfoPanel
      localInfo={localInfo}
      providerInfo={undefined}
      loading={false}
      error={false}
      lockedFields={["episodes.*@1:1"]}
      manualValues={{
        "episodes.title": { "1:1": "手工标题" },
        "episodes.plot": { "1:1": "手工简介" },
      }}
      onFieldPolicyChange={onFieldPolicyChange}
    />);

    fireEvent.click(screen.getByRole("button", { name: "编辑与锁定" }));
    fireEvent.click(screen.getByRole("button", { name: "解锁S01E01 全部字段" }));

    expect(onFieldPolicyChange).toHaveBeenCalledWith([], {});
  });

  it("keeps complete Bangumi credits, character details, and relations folded", () => {
    render(<ScrapeInfoPanel
      provider="bangumi"
      localInfo={localInfo}
      providerInfo={{
        provider: "bangumi", external_id: "315745", title: "租借女友 第二季",
        original_title: "彼女、お借りします 第2期", year: 2022, episode_count: 12,
        image_url: null, summary: "作品简介", premiere_date: "2022-07-01", platform: "TV",
        infobox: [{ key: "放送星期", values: [{ value: "星期五", label: null }] }],
        rating: { score: 7, rank: 4000, total: 1000, distribution: [] },
        meta_tags: ["TV"], tags: [{ name: "恋爱", count: 100, total_count: 1000 }],
        persons: [{ external_id: "12096", name: "古賀一臣", relation: "导演", career: ["producer"], episode_scope: "1-12", image_url: "https://lain.bgm.tv/pic/crt/l/staff.jpg" }],
        characters: [{
          external_id: "74917", name: "水原千鶴", relation: "主角", summary: "女主角详细介绍",
          image_url: "https://lain.bgm.tv/pic/crt/l/character.jpg", birth_year: null,
          birth_month: 4, birth_day: 19, gender: "女", blood_type: "A",
          infobox: [{ key: "身高", values: [{ value: "162cm", label: null }] }],
          actors: [{ external_id: "29233", name: "雨宮天", relation: "声优", career: ["seiyu"], episode_scope: null, image_url: "https://lain.bgm.tv/pic/crt/l/actor.jpg" }],
        }],
        related_subjects: [{ external_id: "349633", name: "続編", title: "租借女友 第三季", relation: "续集", subject_type: 2, image_url: "https://lain.bgm.tv/pic/cover/l/related.jpg" }],
      }}
      loading={false}
      error={false}
    />);

    const complete = screen.getByText("Bangumi 完整条目信息").closest("details");
    expect(complete?.hasAttribute("open")).toBe(false);
    fireEvent.click(screen.getByText("Bangumi 完整条目信息"));
    expect(complete?.hasAttribute("open")).toBe(true);
    expect(screen.getByText("古賀一臣")).toBeTruthy();
    expect(screen.getByText("女主角详细介绍")).toBeTruthy();
    expect(screen.getByText("租借女友 第三季")).toBeTruthy();
    const personImage = screen.getByRole("img", { name: "古賀一臣" });
    expect(personImage.getAttribute("src")).toContain(
      "/artwork/provider/persons/12096?url=",
    );
    fireEvent.error(personImage);
    expect(screen.queryByRole("img", { name: "古賀一臣" })).toBeNull();
  });

  it("groups complete Bangumi subjects by their mapped local season", () => {
    render(<ScrapeInfoPanel
      provider="tmdb"
      generationProvider="bangumi"
      localInfo={localInfo}
      providerInfo={undefined}
      bangumiSeasonGroups={[
        {
          seasonNumber: 1,
          subjects: [
            { externalId: "277554", title: "无职转生 第一季", imageUrl: null, ranges: ["E01–E11"], metadata: undefined, loading: false, error: false },
            { externalId: "325585", title: "无职转生 第一季 第2部分", imageUrl: null, ranges: ["E12–E23"], metadata: undefined, loading: false, error: false },
          ],
        },
        {
          seasonNumber: 2,
          subjects: [
            { externalId: "373247", title: "无职转生 第二季", imageUrl: null, ranges: ["E01–E12"], metadata: undefined, loading: false, error: false },
          ],
        },
      ]}
      loading={false}
      error={false}
    />);

    expect(screen.getByText("2 个本地季度 · 3 个映射条目 · 已加载 0")).toBeTruthy();
    fireEvent.click(screen.getByText("Bangumi 完整条目信息"));
    expect(screen.getByText("无职转生 第一季")).toBeTruthy();
    expect(screen.getByText("无职转生 第一季 第2部分")).toBeTruthy();
    expect(screen.getByText(/Bangumi #325585 · 本地 E12–E23/)).toBeTruthy();
    expect(screen.getByText("无职转生 第二季")).toBeTruthy();
  });

  it("keeps remote-read success separate from an actionable NFO generation error", () => {
    render(<ScrapeInfoPanel
      provider="tmdb"
      generationProvider="bangumi"
      localInfo={localInfo}
      providerInfo={undefined}
      loading={false}
      error={false}
      scrapeMetadataSuccess
      generationError
      generationErrorMessage="Bangumi 条目 277554 无法读取"
    />);

    expect(screen.getByText("已读取最新 TMDB 元数据，尚未写入 NFO")).toBeTruthy();
    expect(screen.getByText("Bangumi 主作品自动补全")).toBeTruthy();
    expect(screen.getByText("NFO 更新失败：Bangumi 条目 277554 无法读取")).toBeTruthy();
  });

  it("explains missing ffmpeg tools after a partial NFO update", () => {
    render(<ScrapeInfoPanel
      localInfo={localInfo}
      providerInfo={undefined}
      loading={false}
      error={false}
      generationResult={{
        media_id: "anime-1", bangumi_id: "414214", provider: "bangumi", external_id: "414214",
        created_files: [], updated_files: Array.from({ length: 14 }, (_, index) => `E${index + 1}.nfo`),
        locked_fields: [], created_artwork_files: [], skipped_files: [], generated_episode_count: 12,
        probe_warnings: Array.from({ length: 12 }, (_, index) => ({ relative_path: `E${index + 1}.mkv`, reason: "FFPROBE_UNAVAILABLE" })),
        artwork_warnings: Array.from({ length: 12 }, (_, index) => ({ relative_path: `E${index + 1}.mkv`, reason: "FFMPEG_UNAVAILABLE" })),
      }}
    />);

    expect(screen.getByText(/更新 14 个 NFO/)).toBeTruthy();
    expect(screen.getByText("12 项：当前服务未找到 ffprobe")).toBeTruthy();
    expect(screen.getByText("12 项：当前服务未找到 ffmpeg")).toBeTruthy();
    expect(screen.getByRole("link", { name: "到设置页配置媒体工具路径" }).getAttribute("href")).toBe("/settings");
  });

  it("reports unmapped regular episodes as safely skipped after a partial update", () => {
    render(<ScrapeInfoPanel
      localInfo={localInfo}
      providerInfo={undefined}
      loading={false}
      error={false}
      generationResult={{
        media_id: "anime-1", bangumi_id: "414214", provider: "bangumi", external_id: "414214",
        created_files: [], updated_files: ["Season 1/E01.nfo"], locked_fields: [],
        created_artwork_files: [], generated_episode_count: 1, probe_warnings: [],
        artwork_warnings: [],
        skipped_files: [{
          relative_path: "Season 1/E02.nfo",
          reason: "EPISODE_SOURCE_NOT_MAPPED",
        }],
      }}
    />);

    expect(screen.getByText(/跳过 1 个未处理文件/)).toBeTruthy();
    expect(screen.getByText("1 项：未配置覆盖该正片的分段来源，已安全跳过")).toBeTruthy();
  });
});
