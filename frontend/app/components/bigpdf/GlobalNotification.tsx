"use client";

import { useEffect } from "react";
import { X, CheckCircle, Info, AlertTriangle, AlertCircle } from "lucide-react";
import { useBigpdfStore, type BigpdfNotification } from "../../stores/bigpdfStore";

interface GlobalNotificationProps {
  maxNotifications?: number;
  autoDismissMs?: number;
}

export function GlobalNotification({
  maxNotifications = 5,
  autoDismissMs = 10000,
}: GlobalNotificationProps) {
  const notifications = useBigpdfStore((s) => s.notifications);
  const removeNotification = useBigpdfStore((s) => s.removeNotification);

  // Auto-dismiss effect
  useEffect(() => {
    if (autoDismissMs <= 0) return;

    const timers: number[] = [];

    notifications.forEach((notification) => {
      const elapsed = Date.now() - notification.createdAt;
      const remaining = Math.max(0, autoDismissMs - elapsed);

      if (remaining <= 0) {
        removeNotification(notification.id);
      } else {
        const timer = window.setTimeout(() => {
          removeNotification(notification.id);
        }, remaining);
        timers.push(timer);
      }
    });

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [notifications, autoDismissMs, removeNotification]);

  const visibleNotifications = notifications.slice(-maxNotifications);

  if (visibleNotifications.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
      {visibleNotifications.map((notification) => (
        <NotificationItem
          key={notification.id}
          notification={notification}
          onDismiss={() => removeNotification(notification.id)}
        />
      ))}
    </div>
  );
}

function NotificationItem({
  notification,
  onDismiss,
}: {
  notification: BigpdfNotification;
  onDismiss: () => void;
}) {
  const config = {
    success: {
      icon: <CheckCircle className="h-5 w-5 text-emerald-400" />,
      borderColor: "border-emerald-800/50",
      bgColor: "bg-emerald-950/90",
      titleColor: "text-emerald-200",
      messageColor: "text-emerald-300/80",
    },
    info: {
      icon: <Info className="h-5 w-5 text-blue-400" />,
      borderColor: "border-blue-800/50",
      bgColor: "bg-blue-950/90",
      titleColor: "text-blue-200",
      messageColor: "text-blue-300/80",
    },
    warning: {
      icon: <AlertTriangle className="h-5 w-5 text-amber-400" />,
      borderColor: "border-amber-800/50",
      bgColor: "bg-amber-950/90",
      titleColor: "text-amber-200",
      messageColor: "text-amber-300/80",
    },
    error: {
      icon: <AlertCircle className="h-5 w-5 text-red-400" />,
      borderColor: "border-red-800/50",
      bgColor: "bg-red-950/90",
      titleColor: "text-red-200",
      messageColor: "text-red-300/80",
    },
  }[notification.type];

  return (
    <div
      className={`rounded-lg border ${config.borderColor} ${config.bgColor} shadow-lg backdrop-blur-sm p-4 animate-in slide-in-from-right fade-in duration-200`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <div className="shrink-0 mt-0.5">{config.icon}</div>
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium ${config.titleColor}`}>
            {notification.title}
          </div>
          {notification.message && (
            <p className={`text-xs mt-0.5 ${config.messageColor}`}>
              {notification.message}
            </p>
          )}
          {notification.action && (
            <button
              type="button"
              onClick={() => {
                notification.action!.onClick();
                onDismiss();
              }}
              className="mt-2 text-xs font-medium text-zinc-300 hover:text-white underline underline-offset-2 transition-colors"
            >
              {notification.action.label}
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 text-zinc-500 hover:text-zinc-300 transition-colors"
          aria-label="关闭通知"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
