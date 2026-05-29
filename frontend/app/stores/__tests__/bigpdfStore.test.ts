import {
  calculateProgress,
  formatDuration,
  formatFileSize,
  estimateDuration,
  mockBigpdfTask,
  mockSystemStatus,
  mockQueueStatus,
  mockNotification,
} from "../bigpdfStore";

describe("bigpdfStore helpers", () => {
  describe("calculateProgress", () => {
    it("returns 0 for queued stage", () => {
      const task = mockBigpdfTask({ status: "queued", stage: "queued", progress: 0 });
      expect(calculateProgress(task)).toBe(0);
    });

    it("returns 2 for uploading stage", () => {
      const task = mockBigpdfTask({ stage: "uploading", progress: 0 });
      expect(calculateProgress(task)).toBe(2);
    });

    it("returns 100 for completed stage", () => {
      const task = mockBigpdfTask({ stage: "completed", progress: 100 });
      expect(calculateProgress(task)).toBe(100);
    });

    it("calculates parsing progress based on time", () => {
      const startedAt = new Date(Date.now() - 540 * 1000).toISOString(); // 9 min elapsed
      const task = mockBigpdfTask({
        stage: "parsing",
        startedAt,
        elapsedTime: 540,
        estimatedRemaining: 540,
      });
      const progress = calculateProgress(task);
      expect(progress).toBeGreaterThan(5);
      expect(progress).toBeLessThan(80);
    });
  });

  describe("formatDuration", () => {
    it("formats seconds", () => {
      expect(formatDuration(45)).toBe("45 秒");
    });

    it("formats minutes", () => {
      expect(formatDuration(120)).toBe("2 分钟");
    });

    it("formats hours and minutes", () => {
      expect(formatDuration(3660)).toBe("1 小时 1 分钟");
    });

    it("formats hours only", () => {
      expect(formatDuration(7200)).toBe("2 小时");
    });
  });

  describe("formatFileSize", () => {
    it("formats bytes", () => {
      expect(formatFileSize(500)).toBe("500 B");
    });

    it("formats kilobytes", () => {
      expect(formatFileSize(1536)).toBe("1.5 KB");
    });

    it("formats megabytes", () => {
      expect(formatFileSize(15728640)).toBe("15.0 MB");
    });
  });

  describe("estimateDuration", () => {
    it("estimates based on file size", () => {
      const duration = estimateDuration(15 * 1024 * 1024, 300);
      expect(duration).toBeGreaterThanOrEqual(300);
    });

    it("returns minimum 5 minutes for small files", () => {
      const duration = estimateDuration(1024, 1);
      expect(duration).toBeGreaterThanOrEqual(300);
    });

    it("considers page count", () => {
      const sizeOnly = estimateDuration(1024 * 1024, 1);
      const withPages = estimateDuration(1024 * 1024, 100);
      expect(withPages).toBeGreaterThanOrEqual(sizeOnly);
    });
  });

  describe("mock data generators", () => {
    it("generates mock task with defaults", () => {
      const task = mockBigpdfTask();
      expect(task.taskId).toBe("t_mock_001");
      expect(task.status).toBe("running");
      expect(task.fileName).toBe("big.pdf");
    });

    it("generates mock task with overrides", () => {
      const task = mockBigpdfTask({ fileName: "custom.pdf", progress: 75 });
      expect(task.fileName).toBe("custom.pdf");
      expect(task.progress).toBe(75);
    });

    it("generates mock system status", () => {
      const status = mockSystemStatus();
      expect(status.hasRunningTask).toBe(true);
      expect(status.queueLength).toBe(1);
    });

    it("generates mock queue status", () => {
      const status = mockQueueStatus();
      expect(status.totalQueueLength).toBe(2);
      expect(status.queuedTasks).toHaveLength(1);
    });

    it("generates mock notification", () => {
      const notification = mockNotification();
      expect(notification.type).toBe("success");
      expect(notification.title).toBe("大 PDF 解析完成");
    });
  });
});
