import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MediaItem } from "../../api/types";
import { libraryApi } from "./api";
import { LibraryPage } from "./LibraryPage";

vi.mock("./api", () => ({
  libraryApi: {
    list: vi.fn(),
  },
}));

const item: MediaItem = {
  id: "anime-1",
  folder_name: "测试番剧",
  title: "测试番剧",
  year: 2026,
  path: "/media/anime-1",
  added_at: "2026-01-01T00:00:00+00:00",
  poster_url: null,
  video_count: 12,
  seasons: [1],
  nfo_present: false,
  external_ids: [],
  status: "unconfigured",
  binding: null,
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <LibraryPage />
    </QueryClientProvider>,
  );
}

describe("LibraryPage", () => {
  beforeEach(() => {
    vi.mocked(libraryApi.list).mockReset().mockResolvedValue([item]);
    window.history.replaceState({}, "", "/");
  });

  it("defaults to recently added and applies name sorting and search", async () => {
    renderPage();

    expect(await screen.findByText("测试番剧")).toBeTruthy();
    expect(libraryApi.list).toHaveBeenCalledWith("", "added_desc");

    fireEvent.change(screen.getByRole("combobox", { name: "排序方式" }), {
      target: { value: "name_asc" },
    });
    await waitFor(() => expect(libraryApi.list).toHaveBeenCalledWith("", "name_asc"));

    fireEvent.change(screen.getByRole("textbox", { name: "搜索番剧" }), {
      target: { value: "测试" },
    });
    await waitFor(() => expect(libraryApi.list).toHaveBeenCalledWith("测试", "name_asc"));
  });
});
