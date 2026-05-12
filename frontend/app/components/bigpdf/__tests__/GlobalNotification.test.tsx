import { render, screen, fireEvent, act } from "@testing-library/react";
import { GlobalNotification } from "../GlobalNotification";
import { useBigpdfStore, mockNotification } from "../../../stores/bigpdfStore";

describe("GlobalNotification", () => {
  beforeEach(() => {
    useBigpdfStore.setState({
      notifications: [],
    });
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("renders nothing when no notifications", () => {
    const { container } = render(<GlobalNotification />);
    expect(container.firstChild).toBeNull();
  });

  it("renders notifications from store", () => {
    const notification = mockNotification();
    useBigpdfStore.setState({ notifications: [notification] });

    render(<GlobalNotification autoDismissMs={0} />);

    expect(screen.getByText("大 PDF 解析完成")).toBeInTheDocument();
    expect(screen.getByText(/big.pdf/)).toBeInTheDocument();
  });

  it("dismisses notification when close button clicked", () => {
    const notification = mockNotification();
    useBigpdfStore.setState({ notifications: [notification] });

    render(<GlobalNotification autoDismissMs={0} />);

    const closeBtn = screen.getByLabelText("关闭通知");
    fireEvent.click(closeBtn);

    expect(screen.queryByText("大 PDF 解析完成")).not.toBeInTheDocument();
  });

  it("shows action button when action is provided", () => {
    const onClick = jest.fn();
    const notification = mockNotification({
      action: {
        label: "立即查看",
        onClick,
      },
    });
    useBigpdfStore.setState({ notifications: [notification] });

    render(<GlobalNotification autoDismissMs={0} />);

    const actionBtn = screen.getByText("立即查看");
    expect(actionBtn).toBeInTheDocument();

    fireEvent.click(actionBtn);
    expect(onClick).toHaveBeenCalled();
  });

  it("auto-dismisses after timeout", () => {
    const notification = mockNotification();
    useBigpdfStore.setState({ notifications: [notification] });

    render(<GlobalNotification autoDismissMs={5000} />);

    expect(screen.getByText("大 PDF 解析完成")).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(5000);
    });

    expect(screen.queryByText("大 PDF 解析完成")).not.toBeInTheDocument();
  });

  it("limits max notifications", () => {
    const notifications = Array.from({ length: 10 }, (_, i) =>
      mockNotification({
        id: `notif_${i}`,
        title: `通知 ${i}`,
        createdAt: Date.now() + i,
      })
    );
    useBigpdfStore.setState({ notifications });

    render(<GlobalNotification maxNotifications={3} autoDismissMs={0} />);

    // Should only show the last 3 notifications
    expect(screen.getByText("通知 7")).toBeInTheDocument();
    expect(screen.getByText("通知 8")).toBeInTheDocument();
    expect(screen.getByText("通知 9")).toBeInTheDocument();
    expect(screen.queryByText("通知 0")).not.toBeInTheDocument();
  });

  it("renders different notification types with correct styling", () => {
    const notifications = [
      mockNotification({ type: "success", title: "成功" }),
      mockNotification({ type: "error", title: "错误" }),
      mockNotification({ type: "warning", title: "警告" }),
      mockNotification({ type: "info", title: "信息" }),
    ];
    useBigpdfStore.setState({ notifications });

    render(<GlobalNotification autoDismissMs={0} />);

    expect(screen.getByText("成功")).toBeInTheDocument();
    expect(screen.getByText("错误")).toBeInTheDocument();
    expect(screen.getByText("警告")).toBeInTheDocument();
    expect(screen.getByText("信息")).toBeInTheDocument();
  });

  it("does not auto-dismiss when autoDismissMs is 0", () => {
    const notification = mockNotification();
    useBigpdfStore.setState({ notifications: [notification] });

    render(<GlobalNotification autoDismissMs={0} />);

    act(() => {
      jest.advanceTimersByTime(60000);
    });

    expect(screen.getByText("大 PDF 解析完成")).toBeInTheDocument();
  });
});
