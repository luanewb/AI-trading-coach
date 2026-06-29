export function Metric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "neutral" | "good" | "warn" | "bad" }) {
  const toneClass = {
    neutral: "text-ink",
    good: "text-good",
    warn: "text-warn",
    bad: "text-bad"
  }[tone];

  return (
    <div className="border border-line bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${toneClass}`}>{value}</p>
    </div>
  );
}
