import { describe, expect, it } from "vitest";
import { imageSource } from "./images";

describe("imageSource", () => {
  it("requests cached thumbnails without dropping refresh versions or provider URLs", () => {
    const local = imageSource("/api/v1/media/show/artwork/seasons/2?v=updated");
    expect(local).toBe("/api/v1/media/show/artwork/seasons/2?v=updated&width=320");
    const portrait = imageSource("/api/v1/media/show/artwork/provider/persons/1?url=https%3A%2F%2Flain.bgm.tv%2Fpic%2Fperson.jpg", 160)!;
    const query = new URL(portrait, "http://localhost").searchParams;
    expect(query.get("url")).toBe("https://lain.bgm.tv/pic/person.jpg");
    expect(query.get("width")).toBe("160");
    expect(imageSource(portrait, 160)).toBe(portrait);
  });
});
