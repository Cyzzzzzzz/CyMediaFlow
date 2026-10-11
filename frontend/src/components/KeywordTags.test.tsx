import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { KeywordTags } from "./KeywordTags";

function Harness() {
  const [words, setWords] = useState(["720p"]);
  return <><KeywordTags label="排除词" value={words} onChange={setWords} /><output>{JSON.stringify(words)}</output><button>保存</button></>;
}

describe("KeywordTags", () => {
  it("adds with Enter, edits on click, cancels with Escape and removes individually", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByLabelText("排除词");
    await user.type(input, " 繁日 {Enter}");
    expect(screen.getByRole("status").textContent).toBe('["720p","繁日"]');
    await user.click(screen.getByRole("button", { name: "编辑排除词 繁日" }));
    await user.clear(input);
    await user.type(input, "简日{Enter}");
    expect(screen.getByRole("status").textContent).toBe('["720p","简日"]');
    await user.click(screen.getByRole("button", { name: "编辑排除词 简日" }));
    await user.clear(input);
    await user.type(input, "取消修改{Escape}");
    expect(screen.getByRole("status").textContent).toBe('["720p","简日"]');
    await user.click(screen.getByRole("button", { name: "删除排除词 简日" }));
    expect(screen.getByRole("status").textContent).toBe('["720p"]');
  });

  it("deduplicates, ignores empty words and commits pending input on save click", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByLabelText("排除词");
    await user.type(input, "{Enter}720P{Enter}");
    expect(screen.getByRole("alert").textContent).toBe("这个排除词已经存在");
    expect(screen.getByRole("status").textContent).toBe('["720p"]');
    await user.clear(input);
    await user.type(input, "合集");
    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(screen.getByRole("status").textContent).toBe('["720p","合集"]');
  });

  it("does not turn IME confirmation into a tag until a separate Enter", () => {
    render(<Harness />);
    const input = screen.getByLabelText("排除词");
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: "简体" } });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    expect(screen.getByRole("status").textContent).toBe('["720p"]');
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByRole("status").textContent).toBe('["720p","简体"]');
  });
});
