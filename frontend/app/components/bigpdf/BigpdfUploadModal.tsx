"use client";

import { useState, useRef, useCallback } from "react";
import { Upload, X, FileText, Clock, AlertCircle } from "lucide-react";
import { useBigpdfStore, formatFileSize, estimateDuration, formatDuration, type BigpdfUploadEstimate } from "../../stores/bigpdfStore";

interface BigpdfUploadModalProps {
  isOpen?: boolean;
  onClose?: () => void;
  onUpload?: (file: File, options: { queueIfBusy: boolean }) => void;
  systemBusy?: boolean;
  currentTaskInfo?: {
    fileName: string;
    estimatedRemaining: number;
  } | null;
  queuePosition?: number;
}

export function BigpdfUploadModal({
  isOpen: externalIsOpen,
  onClose,
  onUpload,
  systemBusy = false,
  currentTaskInfo,
  queuePosition,
}: BigpdfUploadModalProps) {
  const storeIsOpen = useBigpdfStore((s) => s.isUploadModalOpen);
  const setStoreIsOpen = useBigpdfStore((s) => s.setUploadModalOpen);

  const isOpen = externalIsOpen ?? storeIsOpen;
  const closeModal = useCallback(() => {
    setStoreIsOpen(false);
    onClose?.();
  }, [setStoreIsOpen, onClose]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [estimate, setEstimate] = useState<BigpdfUploadEstimate | null>(null);
  const [isReading, setIsReading] = useState(false);
  const [queueIfBusy, setQueueIfBusy] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleFileSelect = useCallback(
    async (file: File) => {
      setSelectedFile(file);
      setIsReading(true);

      let pageCount = 0;

      // Try to read page count from PDF
      try {
        const arrayBuffer = await file.arrayBuffer();
        const text = new TextDecoder().decode(arrayBuffer.slice(0, 50000));
        // Simple regex to find /Type /Page or /Count in PDF header
        const countMatch = text.match(/\/Type\s*\/Pages[\s\S]*?\/Count\s+(\d+)/);
        if (countMatch) {
          pageCount = parseInt(countMatch[1], 10);
        } else {
          // Fallback: count /Type /Page occurrences
          const pageMatches = text.match(/\/Type\s*\/Page\b/g);
          if (pageMatches) {
            pageCount = pageMatches.length;
          }
        }
      } catch {
        pageCount = 0;
      }

      const estimatedDuration = estimateDuration(file.size, pageCount);

      setEstimate({
        fileName: file.name,
        fileSize: file.size,
        pageCount,
        estimatedDuration,
      });
      setIsReading(false);
    },
    []
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        void handleFileSelect(file);
      }
    },
    [handleFileSelect]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file && file.type === "application/pdf") {
        void handleFileSelect(file);
      }
    },
    [handleFileSelect]
  );

  const handleSubmit = useCallback(() => {
    if (!selectedFile) return;
    setIsSubmitting(true);
    onUpload?.(selectedFile, { queueIfBusy });
    // Reset after a delay
    setTimeout(() => {
      setIsSubmitting(false);
      setSelectedFile(null);
      setEstimate(null);
      closeModal();
    }, 500);
  }, [selectedFile, queueIfBusy, onUpload, closeModal]);

  const handleCancel = useCallback(() => {
    setSelectedFile(null);
    setEstimate(null);
    closeModal();
  }, [closeModal]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-lg mx-4 rounded-lg border border-zinc-800 bg-zinc-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-zinc-400" />
            <h2 className="text-base font-medium text-zinc-100">上传大 PDF</h2>
          </div>
          <button
            type="button"
            onClick={handleCancel}
            className="text-zinc-400 hover:text-zinc-200 transition-colors"
            aria-label="关闭"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* System busy warning */}
          {systemBusy && currentTaskInfo && (
            <div className="rounded border border-amber-800/50 bg-amber-950/20 p-3 space-y-2">
              <div className="flex items-center gap-2 text-amber-300">
                <AlertCircle className="h-4 w-4" />
                <span className="text-sm font-medium">系统当前正忙</span>
              </div>
              <div className="text-xs text-amber-200/70 space-y-1">
                <div>
                  当前任务：{currentTaskInfo.fileName}（预计还需{" "}
                  {formatDuration(currentTaskInfo.estimatedRemaining)}）
                </div>
                {queuePosition != null && queuePosition > 0 && (
                  <div>排队位置：第 {queuePosition} 位</div>
                )}
              </div>
            </div>
          )}

          {/* File drop zone */}
          {!selectedFile ? (
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg border-2 border-dashed border-zinc-700 bg-zinc-950/50 p-8 text-center cursor-pointer hover:border-zinc-500 transition-colors"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={handleInputChange}
              />
              <FileText className="h-10 w-10 mx-auto text-zinc-600 mb-3" />
              <p className="text-sm text-zinc-400">
                点击或拖拽 PDF 文件到此处
              </p>
              <p className="text-xs text-zinc-600 mt-1">支持 .pdf 格式</p>
            </div>
          ) : (
            <div className="rounded-lg border border-zinc-700 bg-zinc-950/50 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-zinc-400" />
                  <span className="text-sm text-zinc-200 truncate max-w-[250px]">
                    {selectedFile.name}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedFile(null);
                    setEstimate(null);
                  }}
                  className="text-zinc-500 hover:text-zinc-300"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {isReading ? (
                <div className="text-xs text-zinc-500">正在读取文件信息...</div>
              ) : estimate ? (
                <div className="space-y-2 text-xs">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="text-zinc-500">
                      大小：
                      <span className="text-zinc-300">
                        {formatFileSize(estimate.fileSize)}
                      </span>
                    </div>
                    <div className="text-zinc-500">
                      页数：
                      <span className="text-zinc-300">
                        {estimate.pageCount > 0
                          ? `约 ${estimate.pageCount} 页`
                          : "未知"}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 text-zinc-500">
                    <Clock className="h-3 w-3" />
                    预计解析时间：
                    <span className="text-zinc-300">
                      {formatDuration(estimate.estimatedDuration)}
                    </span>
                  </div>
                  <p className="text-zinc-600 italic">
                    提示：解析耗时较长，您可以关闭页面去处理其他事务，完成后我们会提醒您
                  </p>
                </div>
              ) : null}
            </div>
          )}

          {/* Queue option */}
          {systemBusy && selectedFile && (
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="queue-if-busy"
                checked={queueIfBusy}
                onChange={(e) => setQueueIfBusy(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-blue-500/20"
              />
              <label
                htmlFor="queue-if-busy"
                className="text-xs text-zinc-400 cursor-pointer"
              >
                如果系统正忙，加入队列等待处理
              </label>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-4 border-t border-zinc-800">
          <button
            type="button"
            onClick={handleCancel}
            className="rounded border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-700 transition-colors"
          >
            {systemBusy ? "取消" : "关闭"}
          </button>
          {selectedFile && (
            <button
              type="button"
              disabled={isSubmitting || isReading}
              onClick={handleSubmit}
              className="rounded border border-blue-800 bg-blue-950 px-4 py-2 text-sm text-blue-300 hover:bg-blue-900 disabled:opacity-50 transition-colors"
            >
              {isSubmitting
                ? "提交中..."
                : systemBusy
                ? queueIfBusy
                  ? "排队等待"
                  : "确认上传"
                : "确认并开始解析"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
