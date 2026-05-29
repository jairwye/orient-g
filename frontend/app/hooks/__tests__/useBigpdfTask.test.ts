import { renderHook, waitFor } from "@testing-library/react";
import { useBigpdfTask } from "../useBigpdfTask";
import { useBigpdfStore, mockBigpdfTask } from "../../stores/bigpdfStore";

// Mock auth and smartPoll
jest.mock("../../lib/auth", () => ({
  getAuthHeaders: () => ({ Authorization: "Bearer test" }),
}));

jest.mock("../../lib/smartPoll", () => ({
  useSmartPoll: jest.fn(),
}));

import { useSmartPoll } from "../../lib/smartPoll";

const mockedUseSmartPoll = useSmartPoll as jest.MockedFunction<typeof useSmartPoll>;

describe("useBigpdfTask", () => {
  beforeEach(() => {
    useBigpdfStore.setState({
      activeTask: null,
      notifications: [],
    });
    jest.clearAllMocks();
  });

  it("returns null task when no taskId", () => {
    mockedUseSmartPoll.mockReturnValue({
      data: undefined,
      setData: jest.fn(),
      phase: "idle",
      errorCount: 0,
      trigger: jest.fn(),
    });

    const { result } = renderHook(() =>
      useBigpdfTask({ taskId: null })
    );

    expect(result.current.task).toBeUndefined();
    expect(result.current.isTerminal).toBe(false);
  });

  it("syncs task to store when data changes", async () => {
    const task = mockBigpdfTask();
    mockedUseSmartPoll.mockReturnValue({
      data: task,
      setData: jest.fn(),
      phase: "polling",
      errorCount: 0,
      trigger: jest.fn(),
    });

    renderHook(() => useBigpdfTask({ taskId: "t_001" }));

    await waitFor(() => {
      expect(useBigpdfStore.getState().activeTask).toEqual(task);
    });
  });

  it("detects terminal state correctly", () => {
    const task = mockBigpdfTask({ status: "completed" });
    mockedUseSmartPoll.mockReturnValue({
      data: task,
      setData: jest.fn(),
      phase: "stopped",
      errorCount: 0,
      trigger: jest.fn(),
    });

    const { result } = renderHook(() =>
      useBigpdfTask({ taskId: "t_001" })
    );

    expect(result.current.isTerminal).toBe(true);
  });

  it("calls onComplete when task completes", async () => {
    const onComplete = jest.fn();
    const task = mockBigpdfTask({ status: "completed" });
    mockedUseSmartPoll.mockReturnValue({
      data: task,
      setData: jest.fn(),
      phase: "stopped",
      errorCount: 0,
      trigger: jest.fn(),
    });

    renderHook(() =>
      useBigpdfTask({ taskId: "t_001", onComplete })
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(task);
    });
  });

  it("does not push notifications (handled by completion feed)", async () => {
    const task = mockBigpdfTask({
      status: "completed",
      result: {
        packageId: "pkg_001",
        documentCount: 42,
        folderPath: "/test",
      },
    });
    mockedUseSmartPoll.mockReturnValue({
      data: task,
      setData: jest.fn(),
      phase: "stopped",
      errorCount: 0,
      trigger: jest.fn(),
    });

    renderHook(() => useBigpdfTask({ taskId: "t_001" }));

    await waitFor(() => {
      expect(useBigpdfStore.getState().notifications).toHaveLength(0);
    });
  });

  it("exposes cancelTask function", () => {
    mockedUseSmartPoll.mockReturnValue({
      data: mockBigpdfTask(),
      setData: jest.fn(),
      phase: "polling",
      errorCount: 0,
      trigger: jest.fn(),
    });

    const { result } = renderHook(() =>
      useBigpdfTask({ taskId: "t_001" })
    );

    expect(typeof result.current.cancelTask).toBe("function");
  });

  it("exposes abandonTask function", () => {
    mockedUseSmartPoll.mockReturnValue({
      data: mockBigpdfTask(),
      setData: jest.fn(),
      phase: "polling",
      errorCount: 0,
      trigger: jest.fn(),
    });

    const { result } = renderHook(() =>
      useBigpdfTask({ taskId: "t_001" })
    );

    expect(typeof result.current.abandonTask).toBe("function");
  });

  it("isLoading is false once task data is available", () => {
    mockedUseSmartPoll.mockReturnValue({
      data: mockBigpdfTask(),
      setData: jest.fn(),
      phase: "polling",
      errorCount: 0,
      trigger: jest.fn(),
    });

    const { result } = renderHook(() =>
      useBigpdfTask({ taskId: "t_001", enabled: true })
    );

    expect(result.current.isLoading).toBe(false);
  });

  it("isLoading is true while waiting for first task payload", () => {
    mockedUseSmartPoll.mockReturnValue({
      data: undefined,
      setData: jest.fn(),
      phase: "idle",
      errorCount: 0,
      trigger: jest.fn(),
    });

    const { result } = renderHook(() =>
      useBigpdfTask({ taskId: "t_001", enabled: true })
    );

    expect(result.current.isLoading).toBe(true);
  });

  it("isLoading is false when polling stopped without data", () => {
    mockedUseSmartPoll.mockReturnValue({
      data: undefined,
      setData: jest.fn(),
      phase: "stopped",
      errorCount: 0,
      trigger: jest.fn(),
    });

    const { result } = renderHook(() =>
      useBigpdfTask({ taskId: "t_001", enabled: true })
    );

    expect(result.current.isLoading).toBe(false);
  });
});
