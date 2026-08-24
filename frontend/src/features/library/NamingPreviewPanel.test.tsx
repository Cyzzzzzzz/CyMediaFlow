import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { NamingPreview } from "../../api/types";
import { NamingPreviewPanel } from "./NamingPreviewPanel";

const preview: NamingPreview = {
  media_id: "anime-1",
  operation_mode: "read_only_preview",
  total: 2,
  rename_count: 1,
  unchanged_count: 0,
  review_count: 1,
  conflict_count: 0,
  default_selected_count: 1,
  default_skipped_count: 1,
  entries: [{
    source_relative_path: "raw/[Group][Show][01].mkv",
    target_relative_path: "raw/番剧 S01E01.mkv",
    source_name: "[Group][Show][01].mkv",
    target_name: "番剧 S01E01.mkv",
    status: "rename",
    folder: "raw",
    category: "regular",
    default_selected: true,
    selection_reason: null,
    warnings: [],
    parsed: {
      raw_filename: "[Group][Show][01].mkv", stem: "[Group][Show][01]", extension: ".mkv", file_role: "video",
      title: "Show", title_candidates: ["Show"], year: null, season: null, episode_start: null,
      episode_end: null, absolute_episode_start: 1, absolute_episode_end: 1, special_type: null,
      special_number: null, release_group: "Group", resolution: null, source: null, video_codec: null,
      audio_codec: null, bit_depth: null, version: null, subtitle_language: null, subtitle_flags: [],
      matched_rule_id: "anime.bracket-absolute", confidence: 80, warnings: [], trace: [],
    },
  }, {
    source_relative_path: "raw/[Group][Show][NCOP].mkv",
    target_relative_path: "raw/[Group][Show][NCOP].mkv",
    source_name: "[Group][Show][NCOP].mkv",
    target_name: "[Group][Show][NCOP].mkv",
    status: "review",
    folder: "raw",
    category: "credit",
    default_selected: false,
    selection_reason: "NOT_A_RENAME",
    warnings: ["NON_BANGUMI_CONTENT"],
    parsed: {
      raw_filename: "[Group][Show][NCOP].mkv", stem: "[Group][Show][NCOP]", extension: ".mkv", file_role: "video",
      title: "Show NCOP", title_candidates: ["Show NCOP"], year: null, season: null, episode_start: null,
      episode_end: null, absolute_episode_start: null, absolute_episode_end: null, special_type: null,
      special_number: null, release_group: "Group", resolution: null, source: null, video_codec: null,
      audio_codec: null, bit_depth: null, version: null, subtitle_language: null, subtitle_flags: [],
      matched_rule_id: null, confidence: 35, warnings: ["EPISODE_NOT_FOUND"], trace: [],
    },
  }],
};

describe("NamingPreviewPanel", () => {
  it("shows a compact read-only diff and refreshes it", () => {
    const onRefresh = vi.fn();
    const onSelectionChange = vi.fn();
    render(<NamingPreviewPanel preview={preview} loading={false} error={false} excludedPaths={[]} includedPaths={[]} onSelectionChange={onSelectionChange} onRefresh={onRefresh} />);

    expect(screen.getByText("1 个已选择")).toBeTruthy();
    expect(screen.getByText("2 个文件")).toBeTruthy();
    expect(screen.getByText("[Group][Show][01].mkv")).toBeTruthy();
    expect(screen.getByText("番剧 S01E01.mkv")).toBeTruthy();
    expect(screen.getAllByText("[Group][Show][NCOP].mkv")).toHaveLength(2);
    const episodeCheckbox = screen.getByRole("checkbox", { name: "重命名 [Group][Show][01].mkv" });
    expect((episodeCheckbox as HTMLInputElement).checked).toBe(true);
    const folderToggle = screen.getByRole("button", { name: /raw.*2 个文件/ });
    fireEvent.click(folderToggle);
    expect(folderToggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("checkbox", { name: "重命名 [Group][Show][01].mkv" })).toBeNull();
    fireEvent.click(folderToggle);
    expect(folderToggle.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "取消本文件夹" }));
    expect((screen.getByRole("checkbox", { name: "重命名 [Group][Show][01].mkv" }) as HTMLInputElement).checked).toBe(false);
    expect(onSelectionChange).toHaveBeenLastCalledWith(["raw/[Group][Show][01].mkv"], []);
    fireEvent.click(screen.getByRole("button", { name: /更新预览/ }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });
});
