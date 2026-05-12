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

  it("adds notification on completion", async () => {
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
      const notifications = useBigpdfStore.getState().notifications;
      expect(notifications).toHaveLength(1);
      expect(notifications[0].type).toBe("success");
      expect(notifications[0].title).toBe("大 PDF 解析完成");
    });
  });

  it("adds error notification on failure", async () => {
    const task = mockBigpdfTask({ status: "failed", error: "解析失败" });
    mockedUseSmartPoll.mockReturnValue({
      data: task,
      setData: jest.fn(),
      phase: "stopped",
      errorCount: 0,
      trigger: jest.fn(),
    });

    renderHook(() => useBigpdfTask({ taskId: "t_001" }));

    await waitFor(() => {
      const notifications = useBigpdfStore.getState().notifications;
      expect(notifications).toHaveLength(1);
      expect(notifications[0].type).toBe("error");
      expect(notifications[0].title).toBe("大 PDF 解析失败");
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
});
