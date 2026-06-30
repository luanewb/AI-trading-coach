export function Metric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "good" | "warn" | "bad" }) {
  const toneClass = {
    neutral: "text-zinc-50",
    good: "text-good",
    warn: "text-warn",
    bad: "text-bad"
  }[tone];

  return (
    <div className="panel p-4">
      <p className="kicker">{label}</p>
      <p className={`mt-3 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}
