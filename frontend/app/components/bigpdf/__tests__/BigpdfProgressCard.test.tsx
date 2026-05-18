import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { BigpdfProgressCard } from "../BigpdfProgressCard";
import { useBigpdfStore, mockBigpdfTask } from "../../../stores/bigpdfStore";

describe("BigpdfProgressCard", () => {
  beforeEach(() => {
    useBigpdfStore.setState({
      activeTask: null,
      isProgressCardCollapsed: false,
    });
  });

  it("renders nothing when no task", () => {
    const { container } = render(<BigpdfProgressCard task={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders task info when task is provided", () => {
    const task = mockBigpdfTask();
    render(<BigpdfProgressCard task={task} />);

    expect(screen.getByText("big.pdf")).toBeInTheDocument();
    expect(screen.getByText(/解析中/)).toBeInTheDocument();
  });

  it("renders from store when no external task provided", () => {
    const task = mockBigpdfTask();
    useBigpdfStore.setState({ activeTask: task });

    render(<BigpdfProgressCard />);

    expect(screen.getByText("big.pdf")).toBeInTheDocument();
  });

  it("toggles collapse state", () => {
    const task = mockBigpdfTask();
    render(<BigpdfProgressCard task={task} />);

    // Should show expanded content initially
    expect(screen.getByText(/进度/)).toBeInTheDocument();

    // Click collapse button
    const collapseBtn = screen.getByLabelText("折叠");
    fireEvent.click(collapseBtn);

    // Content should be hidden
    expect(screen.queryByText(/进度/)).not.toBeInTheDocument();
  });

  it("shows abandon confirmation when abandon button clicked", () => {
    const task = mockBigpdfTask({ status: "running", stage: "parsing" });
    render(<BigpdfProgressCard task={task} />);

    const abandonBtn = screen.getByText("停止跟踪");
    fireEvent.click(abandonBtn);

    expect(screen.getByText(/取消后/)).toBeInTheDocument();
    expect(screen.getByText("继续跟踪")).toBeInTheDocument();
    expect(screen.getByText("确认取消")).toBeInTheDocument();
  });

  it("shows force cancel confirmation for owner", () => {
    const task = mockBigpdfTask({ status: "running", stage: "parsing", isMine: true });
    render(<BigpdfProgressCard task={task} onForceCancel={jest.fn()} />);

    const forceBtn = screen.getByText("强制终止");
    fireEvent.click(forceBtn);

    expect(screen.getByText(/强制终止将立即停止/)).toBeInTheDocument();
  });

  it("shows completed status correctly", () => {
    const task = mockBigpdfTask({
      status: "completed",
      stage: "completed",
      progress: 100,
      result: {
        packageId: "pkg_001",
        documentCount: 42,
        folderPath: "/大PDF-big.pdf",
      },
    });
    render(<BigpdfProgressCard task={task} />);

    expect(screen.getByText(/已完成/)).toBeInTheDocument();
    expect(screen.getByText(/已生成 42 个知识片段/)).toBeInTheDocument();
  });

  it("shows error message when task failed", () => {
    const task = mockBigpdfTask({
      status: "failed",
      stage: "parsing",
      error: "解析超时",
    });
    render(<BigpdfProgressCard task={task} />);

    expect(screen.getByText("解析超时")).toBeInTheDocument();
  });

  it("calls onCancel when cancel button clicked", () => {
    const onCancel = jest.fn();
    const task = mockBigpdfTask({ status: "running", stage: "parsing" });
    render(<BigpdfProgressCard task={task} onCancel={onCancel} />);

    const cancelBtn = screen.getByText("取消任务");
    fireEvent.click(cancelBtn);

    expect(onCancel).toHaveBeenCalled();
  });

  it("calls onAbandon when abandon confirmed", () => {
    const onAbandon = jest.fn();
    const task = mockBigpdfTask({ status: "running", stage: "parsing" });
    render(<BigpdfProgressCard task={task} onAbandon={onAbandon} />);

    fireEvent.click(screen.getByText("停止跟踪"));
    fireEvent.click(screen.getByText("确认取消"));

    expect(onAbandon).toHaveBeenCalled();
  });
});
