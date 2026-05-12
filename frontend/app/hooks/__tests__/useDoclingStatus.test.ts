import { renderHook, waitFor } from "@testing-library/react";
import { useDoclingStatus } from "../useDoclingStatus";
import { useBigpdfStore, mockSystemStatus, mockQueueStatus } from "../../stores/bigpdfStore";

// Mock auth
jest.mock("../../lib/auth", () => ({
  getAuthHeaders: () => ({ Authorization: "Bearer test" }),
}));

// Mock fetch
global.fetch = jest.fn();
const mockedFetch = fetch as jest.MockedFunction<typeof fetch>;

describe("useDoclingStatus", () => {
  beforeEach(() => {
    useBigpdfStore.setState({
      systemStatus: null,
      queueStatus: null,
    });
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("fetches status on mount", async () => {
    const systemStatus = mockSystemStatus();
    const queueStatus = mockQueueStatus();

    mockedFetch.mockImplementation((url) => {
      if (url === "/api/knowledge/bigpdf/status") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(systemStatus),
        } as Response);
      }
      if (url === "/api/knowledge/bigpdf/queue") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(queueStatus),
        } as Response);
      }
      return Promise.reject(new Error("Unknown URL"));
    });

    renderHook(() => useDoclingStatus({ autoStart: true, pollInterval: 10000 }));

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/knowledge/bigpdf/status",
        expect.any(Object)
      );
    });

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledWith(
        "/api/knowledge/bigpdf/queue",
        expect.any(Object)
      );
    });
  });

  it("does not fetch when autoStart is false", () => {
    renderHook(() => useDoclingStatus({ autoStart: false }));

    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it("returns isBusy when system has running task", () => {
    const systemStatus = mockSystemStatus({ hasRunningTask: true });
    useBigpdfStore.setState({ systemStatus });

    const { result } = renderHook(() =>
      useDoclingStatus({ autoStart: false })
    );

    expect(result.current.isBusy).toBe(true);
  });

  it("returns isMyTaskRunning when task is mine", () => {
    const systemStatus = mockSystemStatus({
      hasRunningTask: true,
      runningTask: mockSystemStatus().runningTask
        ? { ...mockSystemStatus().runningTask!, isMine: true }
        : undefined,
    });
    useBigpdfStore.setState({ systemStatus });

    const { result } = renderHook(() =>
      useDoclingStatus({ autoStart: false })
    );

    expect(result.current.isMyTaskRunning).toBe(true);
  });

  it("returns myQueuePosition from system status", () => {
    const systemStatus = mockSystemStatus({ queuePosition: 3 });
    useBigpdfStore.setState({ systemStatus });

    const { result } = renderHook(() =>
      useDoclingStatus({ autoStart: false })
    );

    expect(result.current.myQueuePosition).toBe(3);
  });

  it("exposes forceCancel function", () => {
    const { result } = renderHook(() =>
      useDoclingStatus({ autoStart: false })
    );

    expect(typeof result.current.forceCancel).toBe("function");
  });

  it("handles fetch errors", async () => {
    mockedFetch.mockRejectedValue(new Error("Network error"));

    const { result } = renderHook(() =>
      useDoclingStatus({ autoStart: true, pollInterval: 10000 })
    );

    await waitFor(() => {
      expect(result.current.error).toBeTruthy();
    });
  });

  it("polls at specified interval", async () => {
    mockedFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockSystemStatus()),
    } as Response);

    renderHook(() =>
      useDoclingStatus({ autoStart: true, pollInterval: 5000 })
    );

    // Wait for initial fetch
    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledTimes(2); // status + queue
    });

    // Advance timer
    jest.advanceTimersByTime(5000);

    await waitFor(() => {
      expect(mockedFetch).toHaveBeenCalledTimes(4); // another status + queue
    });
  });
});
