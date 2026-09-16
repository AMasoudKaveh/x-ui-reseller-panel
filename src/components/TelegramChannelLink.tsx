export const TELEGRAM_CHANNEL_URL = "https://t.me/MasoudOpenSourceLab";

export function TelegramIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M21.78 2.23a1.12 1.12 0 0 0-1.16-.13L2.4 9.16c-1.25.49-1.23 1.21-.22 1.52l4.65 1.45 1.78 5.47c.22.67.4.93.79.93.3 0 .54-.14.82-.41l2.56-2.49 4.84 3.57c.89.49 1.53.24 1.75-.83l3.15-14.85c.29-1.3-.5-1.74-.74-1.29ZM8.16 11.77l9.68-6.11c.48-.29.92-.14.56.18l-7.99 7.21-.31 3.31-1.94-4.59Z"
      />
    </svg>
  );
}
