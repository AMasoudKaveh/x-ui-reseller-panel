import type { LucideIcon } from "lucide-react";

type Props = {
  icon: LucideIcon;
  title: string;
  value: string;
  tag?: string;
  ring?: number;
  footerRight?: React.ReactNode;
  wide?: boolean;
};

export default function MetricCard({
  icon: Icon,
  title,
  value,
  tag,
  ring,
  footerRight,
  wide
}: Props) {
  const ringStyle =
    typeof ring === "number"
      ? {
          background: `conic-gradient(
            var(--accent) ${Math.min(Math.max(ring, 0), 100) * 3.6}deg,
            var(--ring-track) 0deg
          )`
        }
      : undefined;

  return (
    <section className={`dashboard-metric-card ${wide ? "dashboard-metric-wide" : ""}`}>
      <div className="dashboard-metric-header">
        <div className="dashboard-metric-title-wrap">
          <div className="metric-icon">
            <Icon size={21} strokeWidth={1.8} />
          </div>
          <span className="dashboard-metric-title">{title}</span>
        </div>

        {typeof ring === "number" ? (
          <div className="dashboard-ring" style={ringStyle}>
            <div className="dashboard-ring-inner" />
          </div>
        ) : null}
      </div>

      <div className="dashboard-metric-body-row">
        <div className="dashboard-metric-value">{value}</div>
        {tag ? <div className="dashboard-metric-tag">{tag}</div> : null}
      </div>

      {footerRight ? (
        <div className="dashboard-metric-footer">
          <div />
          <div>{footerRight}</div>
        </div>
      ) : null}
    </section>
  );
}
