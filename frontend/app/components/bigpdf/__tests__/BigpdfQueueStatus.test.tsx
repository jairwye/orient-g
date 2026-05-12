import { render, screen } from "@testing-library/react";
import { BigpdfQueueStatus } from "../BigpdfQueueStatus";
import { useBigpdfStore, mockQueueStatus } from "../../../stores/bigpdfStore";

describe("BigpdfQueueStatus", () => {
  beforeEach(() => {
    useBigpdfStore.setState({
      queueStatus: null,
    });
  });

  it("shows loading state when no queue status", () => {
    render(<BigpdfQueueStatus queueStatus={null} />);

    expect(screen.getByText("加载队列状态...")).toBeInTheDocument();
  });

  it("renders running task and queued tasks", () => {
    const queueStatus = mockQueueStatus();
    render(<BigpdfQueueStatus queueStatus={queueStatus} />);

    expect(screen.getByText("队列状态")).toBeInTheDocument();
    expect(screen.getByText("正在处理")).toBeInTheDocument();
    expect(screen.getByText("big.pdf")).toBeInTheDocument();
    expect(screen.getByText("排队中")).toBeInTheDocument();
    expect(screen.getByText("another.pdf")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
  });

  it("renders from store when no external prop", () => {
    const queueStatus = mockQueueStatus();
    useBigpdfStore.setState({ queueStatus });

    render(<BigpdfQueueStatus />);

    expect(screen.getByText("队列状态")).toBeInTheDocument();
    expect(screen.getByText("big.pdf")).toBeInTheDocument();
  });

  it("shows empty state when no tasks", () => {
    const queueStatus = mockQueueStatus({
      runningTask: undefined,
      queuedTasks: [],
      totalQueueLength: 0,
    });

    render(<BigpdfQueueStatus queueStatus={queueStatus} />);

    expect(screen.getByText("当前无运行中的任务")).toBeInTheDocument();
    expect(screen.getByText("队列为空，可以立即上传新文件")).toBeInTheDocument();
  });

  it("shows total queue length", () => {
    const queueStatus = mockQueueStatus({ totalQueueLength: 5 });
    render(<BigpdfQueueStatus queueStatus={queueStatus} />);

    expect(screen.getByText(/共 5 个任务/)).toBeInTheDocument();
  });

  it("shows owner names", () => {
    const queueStatus = mockQueueStatus({
      queuedTasks: [
        {
          taskId: "t_003",
          owner: "alice",
          fileName: "alice.pdf",
          queuedAt: new Date().toISOString(),
          position: 1,
        },
      ],
    });

    render(<BigpdfQueueStatus queueStatus={queueStatus} />);

    expect(screen.getByText("alice")).toBeInTheDocument();
  });
});
