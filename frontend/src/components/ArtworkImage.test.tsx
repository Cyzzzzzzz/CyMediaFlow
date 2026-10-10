import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ArtworkImage } from "./ArtworkImage";

afterEach(() => vi.unstubAllGlobals());

it("waits until hidden artwork approaches the viewport before requesting it", () => {
  let intersect: IntersectionObserverCallback = () => {};
  const disconnect = vi.fn();
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback: IntersectionObserverCallback) { intersect = callback; }
    observe() {}
    disconnect = disconnect;
  });
  render(<ArtworkImage src="/portrait.webp" alt="角色" />);
  expect(screen.getByAltText("角色").getAttribute("src")).toBeNull();
  act(() => intersect([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
  expect(screen.getByAltText("角色").getAttribute("src")).toBe("/portrait.webp");
  expect(disconnect).toHaveBeenCalled();
});

it("starts priority posters immediately", () => {
  render(<ArtworkImage src="/poster.webp" alt="海报" priority />);
  expect(screen.getByAltText("海报").getAttribute("src")).toBe("/poster.webp");
  expect(screen.getByAltText("海报").getAttribute("loading")).toBe("eager");
});
