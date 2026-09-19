import { fireEvent, render, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useScreeningShortcuts } from "./useScreeningShortcuts";

describe("useScreeningShortcuts", () => {
  it("calls the handler bound to a letter key, whatever its case", () => {
    const include = vi.fn();
    renderHook(() => useScreeningShortcuts({ i: include }));

    fireEvent.keyDown(document.body, { key: "i" });
    fireEvent.keyDown(document.body, { key: "I" });

    expect(include).toHaveBeenCalledTimes(2);
  });

  it("ignores letters typed into a text field, textarea, select or editable element", () => {
    const include = vi.fn();
    renderHook(() => useScreeningShortcuts({ i: include }));
    const { container } = render(
      <div>
        <input aria-label="text" />
        <textarea aria-label="area" />
        <select aria-label="pick">
          <option>a</option>
        </select>
        <div contentEditable suppressContentEditableWarning aria-label="editable" />
      </div>
    );

    for (const element of container.querySelectorAll("input, textarea, select, [contenteditable]")) {
      fireEvent.keyDown(element, { key: "i" });
    }

    expect(include).not.toHaveBeenCalled();
  });

  it("still fires from a focused radio button, so choosing a decision does not trap the keys", () => {
    const exclude = vi.fn();
    renderHook(() => useScreeningShortcuts({ e: exclude }));
    const { getByRole } = render(<input type="radio" aria-label="include" />);

    fireEvent.keyDown(getByRole("radio"), { key: "e" });

    expect(exclude).toHaveBeenCalledTimes(1);
  });

  it("leaves browser and OS shortcuts alone when a modifier is held", () => {
    const include = vi.fn();
    renderHook(() => useScreeningShortcuts({ i: include }));

    fireEvent.keyDown(document.body, { key: "i", ctrlKey: true });
    fireEvent.keyDown(document.body, { key: "i", metaKey: true });
    fireEvent.keyDown(document.body, { key: "i", altKey: true });

    expect(include).not.toHaveBeenCalled();
  });

  it("fires mod+enter on Ctrl+Enter or Cmd+Enter, even from inside a textarea", () => {
    const record = vi.fn();
    renderHook(() => useScreeningShortcuts({ "mod+enter": record }));
    const { getByLabelText } = render(<textarea aria-label="reason" />);

    fireEvent.keyDown(getByLabelText("reason"), { key: "Enter", ctrlKey: true });
    fireEvent.keyDown(getByLabelText("reason"), { key: "Enter", metaKey: true });
    fireEvent.keyDown(getByLabelText("reason"), { key: "Enter" });

    expect(record).toHaveBeenCalledTimes(2);
  });

  it("uses the latest handlers without re-binding on every render", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ handler }) => useScreeningShortcuts({ j: handler }), {
      initialProps: { handler: first },
    });

    rerender({ handler: second });
    fireEvent.keyDown(document.body, { key: "j" });

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("stops listening once unmounted", () => {
    const include = vi.fn();
    const { unmount } = renderHook(() => useScreeningShortcuts({ i: include }));

    unmount();
    fireEvent.keyDown(document.body, { key: "i" });

    expect(include).not.toHaveBeenCalled();
  });
});
