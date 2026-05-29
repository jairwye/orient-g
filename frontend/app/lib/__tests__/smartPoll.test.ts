import { act, renderHook, waitFor } from "@testing-library/react";
import { useSmartPoll } from "../smartPoll";

type Task = { id: string; status: string };

const baseOpts = {
  isTerminal: (data: Task) => data.status === "completed",
  isActive: (data: Task) => data.status === "running",
  activeMs: 50,
  stableMs: 200,
  errorMaxMs: 1000,
  errorCooldownAfter: 3,
  errorCooldownMs: 5000,
};

describe("useSmartPoll", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("loads data when enabled with pollKey", async () => {
    const load = jest.fn().mockResolvedValue({ id: "t1", status: "running" });

    const { result } = renderHook(() =>
      useSmartPoll<Task>({
        enabled: true,
        pollKey: "t1",
        load,
        ...baseOpts,
      }),
    );

    await act(async () => {
      jest.runOnlyPendingTimers();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.data).toEqual({ id: "t1", status: "running" });
    });
    expect(load).toHaveBeenCalled();
  });

  it("resumes polling after enabled flips from false to true", async () => {
    const load = jest.fn().mockResolvedValue({ id: "t1", status: "running" });

    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useSmartPoll<Task>({
          enabled,
          pollKey: "t1",
          load,
          ...baseOpts,
        }),
      { initialProps: { enabled: false } },
    );

    expect(result.current.data).toBeUndefined();

    rerender({ enabled: true });

    await act(async () => {
      jest.runOnlyPendingTimers();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.data).toEqual({ id: "t1", status: "running" });
    });
    expect(load).toHaveBeenCalled();
  });

  it("does not get stuck in stopped phase while enabled and non-terminal", async () => {
    const load = jest.fn().mockResolvedValue({ id: "t1", status: "running" });

    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useSmartPoll<Task>({
          enabled,
          pollKey: "t1",
          load,
          ...baseOpts,
        }),
      { initialProps: { enabled: false } },
    );

    rerender({ enabled: true });

    await act(async () => {
      jest.advanceTimersByTime(300);
      await Promise.resolve();
    });

    expect(result.current.phase).not.toBe("stopped");
    await waitFor(() => {
      expect(result.current.data).toEqual({ id: "t1", status: "running" });
    });
  });
});
