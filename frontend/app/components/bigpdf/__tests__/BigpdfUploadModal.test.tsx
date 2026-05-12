import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BigpdfUploadModal } from "../BigpdfUploadModal";
import { useBigpdfStore } from "../../../stores/bigpdfStore";

describe("BigpdfUploadModal", () => {
  beforeEach(() => {
    useBigpdfStore.setState({
      isUploadModalOpen: true,
    });
  });

  afterEach(() => {
    useBigpdfStore.setState({ isUploadModalOpen: false });
  });

  it("renders when open", () => {
    render(<BigpdfUploadModal />);

    expect(screen.getByText("上传大 PDF")).toBeInTheDocument();
    expect(screen.getByText(/点击或拖拽/)).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    useBigpdfStore.setState({ isUploadModalOpen: false });
    const { container } = render(<BigpdfUploadModal />);

    expect(container.firstChild).toBeNull();
  });

  it("shows system busy warning when busy", () => {
    render(
      <BigpdfUploadModal
        systemBusy={true}
        currentTaskInfo={{
          fileName: "current.pdf",
          estimatedRemaining: 900,
        }}
        queuePosition={2}
      />
    );

    expect(screen.getByText("系统当前正忙")).toBeInTheDocument();
    expect(screen.getByText(/current.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/排队位置：第 2 位/)).toBeInTheDocument();
  });

  it("closes when cancel button clicked", () => {
    const onClose = jest.fn();
    render(<BigpdfUploadModal onClose={onClose} />);

    fireEvent.click(screen.getByText("关闭"));

    expect(onClose).toHaveBeenCalled();
  });

  it("handles file selection and shows estimate", async () => {
    const onUpload = jest.fn();
    const user = userEvent.setup();

    render(<BigpdfUploadModal onUpload={onUpload} systemBusy={false} />);

    // Create a mock PDF file
    const file = new File(["%PDF-1.4\n/Type /Pages /Count 10\n/Type /Page"], "test.pdf", {
      type: "application/pdf",
    });

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText("test.pdf")).toBeInTheDocument();
    });

    // Should show file info
    expect(screen.getByText(/大小：/)).toBeInTheDocument();
  });

  it("shows queue option when system is busy and file selected", async () => {
    const user = userEvent.setup();

    render(<BigpdfUploadModal systemBusy={true} currentTaskInfo={{ fileName: "busy.pdf", estimatedRemaining: 600 }} />);

    const file = new File(["%PDF-1.4"], "test.pdf", { type: "application/pdf" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByLabelText(/如果系统正忙/)).toBeInTheDocument();
    });
  });

  it("calls onUpload with correct options", async () => {
    const onUpload = jest.fn();
    const user = userEvent.setup();

    render(<BigpdfUploadModal onUpload={onUpload} systemBusy={false} />);

    const file = new File(["%PDF-1.4"], "test.pdf", { type: "application/pdf" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText("确认并开始解析")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("确认并开始解析"));

    await waitFor(() => {
      expect(onUpload).toHaveBeenCalledWith(
        expect.any(File),
        expect.objectContaining({ queueIfBusy: true })
      );
    });
  });

  it("shows correct button text when system busy", async () => {
    const user = userEvent.setup();

    render(<BigpdfUploadModal systemBusy={true} currentTaskInfo={{ fileName: "busy.pdf", estimatedRemaining: 600 }} />);

    const file = new File(["%PDF-1.4"], "test.pdf", { type: "application/pdf" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText("排队等待")).toBeInTheDocument();
    });
  });
});
