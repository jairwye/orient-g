export default function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-2">
      <span
        className="inline-block h-1.5 w-1.5 rounded-full bg-zinc-400"
        style={{ animation: "typingBounce 1.4s infinite ease-in-out both", animationDelay: "0ms" }}
      />
      <span
        className="inline-block h-1.5 w-1.5 rounded-full bg-zinc-400"
        style={{ animation: "typingBounce 1.4s infinite ease-in-out both", animationDelay: "160ms" }}
      />
      <span
        className="inline-block h-1.5 w-1.5 rounded-full bg-zinc-400"
        style={{ animation: "typingBounce 1.4s infinite ease-in-out both", animationDelay: "320ms" }}
      />
      <style jsx>{`
        @keyframes typingBounce {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
