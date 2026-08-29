import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { NfoPreview } from "../../api/types";
import { NfoPreviewPanel } from "./NfoPreviewPanel";

const parsed = {
  raw_filename: "[Group][Show][01].mkv", stem: "[Group][Show][01]", extension: ".mkv", file_role: "video" as const,
  title: "Show", title_candidates: ["Show"], year: null, season: null, episode_start: null,
  episode_end: null, absolute_episode_start: 1, absolute_episode_end: 1, special_type: null,
  special_number: null, release_group: "Group", resolution: null, source: null, video_codec: null,
  audio_codec: null, bit_depth: null, version: null, subtitle_language: null, subtitle_flags: [],
  matched_rule_id: "anime.bracket-absolute", confidence: 80, warnings: [], trace: [],
};

const preview: NfoPreview = {
  media_id: "anime-1", operation_mode: "read_only_preview", total: 2, create_count: 1,
  rename_count: 0, unchanged_count: 0, review_count: 1, conflict_count: 0,
  default_selected_count: 1, default_skipped_count: 1,
  entries: [{
    video_relative_path: "raw/[Group][Show][01].mkv", video_name: "[Group][Show][01].mkv",
    source_nfo_relative_path: null, source_nfo_name: null,
    target_nfo_relative_path: "raw/[Group][Show][01].nfo", target_nfo_name: "[Group][Show][01].nfo",
    action: "create", folder: "raw", category: "regular", default_selected: true,
    selection_reason: null, parsed, warnings: [],
  }, {
    video_relative_path: "raw/[Group][Show][NCOP].mkv", video_name: "[Group][Show][NCOP].mkv",
    source_nfo_relative_path: null, source_nfo_name: null,
    target_nfo_relative_path: "raw/[Group][Show][NCOP].nfo", target_nfo_name: "[Group][Show][NCOP].nfo",
    action: "review", folder: "raw", category: "credit", default_selected: false,
    selection_reason: "NON_BANGUMI_CONTENT", parsed: { ...parsed, raw_filename: "[Group][Show][NCOP].mkv", absolute_episode_start: null }, warnings: ["NON_BANGUMI_CONTENT"],
  }],
};

describe("NfoPreviewPanel", () => {
  it("keeps video names read-only and supports folder controls", () => {
    const onSelectionChange = vi.fn();
    render(<NfoPreviewPanel preview={preview} loading={false} error={false} excludedPaths={[]} excludedFolders={[]} includedPaths={[]} onSelectionChange={onSelectionChange} onRefresh={vi.fn()} />);

    expect(screen.getByText("优先显示上次分析缓存；视频文件名保持不变")).toBeTruthy();
    expect(screen.getByText((content) => content.includes("对应视频：[Group][Show][01].mkv"))).toBeTruthy();
    expect(screen.getByText("[Group][Show][01].nfo")).toBeTruthy();
    const checkbox = screen.getByRole("checkbox", { name: "处理 NFO [Group][Show][01].nfo" });
    expect((checkbox as HTMLInputElement).checked).toBe(true);

    const folderToggle = screen.getByRole("button", { name: /raw.*2 个文件/ });
    fireEvent.click(folderToggle);
    expect(folderToggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(folderToggle);
    fireEvent.click(screen.getByRole("button", { name: "取消本文件夹" }));
    expect(onSelectionChange).toHaveBeenLastCalledWith(["raw/[Group][Show][01].nfo"], [], []);
  });

  it("allows an existing sidecar to be selected for managed update", () => {
    const existing = {
      ...preview,
      total: 1,
      create_count: 0,
      unchanged_count: 1,
      review_count: 0,
      default_skipped_count: 0,
      entries: [{
        ...preview.entries[0],
        source_nfo_relative_path: "raw/[Group][Show][01].nfo",
        source_nfo_name: "[Group][Show][01].nfo",
        action: "unchanged" as const,
      }],
    };
    render(<NfoPreviewPanel preview={existing} loading={false} error={false} excludedPaths={[]} excludedFolders={[]} includedPaths={[]} onSelectionChange={vi.fn()} onRefresh={vi.fn()} />);

    const checkbox = screen.getByRole("checkbox", { name: "处理 NFO [Group][Show][01].nfo" });
    expect((checkbox as HTMLInputElement).disabled).toBe(false);
    expect((checkbox as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("待更新")).toBeTruthy();
  });

  it("records an explicit skip for an unmapped segmented episode", () => {
    const onSelectionChange = vi.fn();
    const unmapped = {
      ...preview,
      total: 1,
      create_count: 1,
      review_count: 0,
      default_selected_count: 0,
      default_skipped_count: 1,
      entries: [{
        ...preview.entries[0],
        default_selected: false,
        selection_reason: "EPISODE_SOURCE_NOT_MAPPED",
        warnings: ["EPISODE_SOURCE_NOT_MAPPED"],
      }],
    };
    render(<NfoPreviewPanel preview={unmapped} loading={false} error={false} excludedPaths={[]} excludedFolders={[]} includedPaths={[]} onSelectionChange={onSelectionChange} onRefresh={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "跳过此文件" }));
    expect(onSelectionChange).toHaveBeenLastCalledWith(["raw/[Group][Show][01].nfo"], [], []);
  });

  it("persists a manual folder exclusion even when the folder contains skipped extras", () => {
    const onSelectionChange = vi.fn();
    const { rerender } = render(<NfoPreviewPanel preview={preview} loading={false} error={false} excludedPaths={[]} excludedFolders={[]} includedPaths={[]} onSelectionChange={onSelectionChange} onRefresh={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "排除文件夹" }));

    expect(onSelectionChange).toHaveBeenLastCalledWith([], [], ["raw"]);
    rerender(<NfoPreviewPanel preview={preview} loading={false} error={false} excludedPaths={[]} excludedFolders={["raw"]} includedPaths={[]} onSelectionChange={onSelectionChange} onRefresh={vi.fn()} />);
    expect((screen.getByRole("checkbox", { name: "处理 NFO [Group][Show][01].nfo" }) as HTMLInputElement).disabled).toBe(true);
    expect(screen.getAllByText("已手动排除文件夹")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "取消排除" })).toBeTruthy();
  });
});
