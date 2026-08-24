import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MediaItem } from "../../api/types";
import { PosterCard } from "./PosterCard";

const item: MediaItem = {
  id: "anime-1",
  folder_name: "测试番剧",
  title: "测试番剧",
  year: 2026,
  path: "/media/anime-1",
  poster_url: "https://example.test/poster.jpg",
  video_count: 12,
  seasons: [1],
  nfo_present: false,
  external_ids: [],
  status: "unconfigured",
  binding: null,
};

describe("PosterCard", () => {
  it("keeps the card compact and opens the selected anime", () => {
    const onOpen = vi.fn();
    render(<PosterCard item={item} selected={false} onOpen={onOpen} />);

    expect(screen.getByText("测试番剧")).toBeTruthy();
    expect(screen.getByText("待匹配")).toBeTruthy();
    fireEvent.click(screen.getByRole("button"));
    expect(onOpen).toHaveBeenCalledWith(item);
  });
});
