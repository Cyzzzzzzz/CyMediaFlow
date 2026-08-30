import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SubtitleMatchPreview } from "../../api/types";
import { SubtitleMatchPanel } from "./SubtitleMatchPanel";

const preview: SubtitleMatchPreview = {
  media_id: "anime-1",
  operation_mode: "read_only_preview",
  total: 2,
  rename_count: 2,
  unchanged_count: 0,
  review_count: 0,
  conflict_count: 0,
  default_selected_count: 2,
  entries: [
    {
      source_relative_path: "Season 1/download.01.sc.ass",
      source_name: "download.01.sc.ass",
      target_relative_path: "Season 1/Show S01E01.sc.ass",
      target_name: "Show S01E01.sc.ass",
      video_relative_path: "Season 1/Show S01E01.mkv",
      video_name: "Show S01E01.mkv",
      folder: "Season 1",
      season_number: 1,
      episode_number: 1,
      language: "zh-CN",
      language_tag: "sc",
      status: "rename",
      default_selected: true,
      reason: null,
      warnings: [],
    },
    {
      source_relative_path: "Season 1/download.01.tc.ass",
      source_name: "download.01.tc.ass",
      target_relative_path: "Season 1/Show S01E01.tc.ass",
      target_name: "Show S01E01.tc.ass",
      video_relative_path: "Season 1/Show S01E01.mkv",
      video_name: "Show S01E01.mkv",
      folder: "Season 1",
      season_number: 1,
      episode_number: 1,
      language: "zh-TW",
      language_tag: "tc",
      status: "rename",
      default_selected: true,
      reason: null,
      warnings: [],
    },
  ],
};

describe("SubtitleMatchPanel", () => {
  it("shows distinct simplified and traditional targets and requires inline confirmation", () => {
    const onRename = vi.fn();
    render(<SubtitleMatchPanel preview={preview} loading={false} error={false} renaming={false} renameError={false} result={undefined} onRefresh={vi.fn()} onRename={onRename} />);

    expect(screen.getByText("Show S01E01.sc.ass")).toBeTruthy();
    expect(screen.getByText("Show S01E01.tc.ass")).toBeTruthy();
    expect(screen.getByText("sc")).toBeTruthy();
    expect(screen.getByText("tc")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "重命名字幕" }));
    expect(onRename).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认重命名" }));
    expect(onRename).toHaveBeenCalledTimes(1);
  });
});
