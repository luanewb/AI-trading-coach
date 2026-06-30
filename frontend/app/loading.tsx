export default function Loading() {
  return (
    <div className="page-frame">
      <header className="page-header">
        <div>
          <p className="kicker">MT5 Risk Dashboard</p>
          <h2 className="page-title">Loading dashboard</h2>
        </div>
      </header>
      <section className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="panel h-28 animate-pulse p-4">
            <div className="h-3 w-24 rounded bg-zinc-800" />
            <div className="mt-5 h-8 w-32 rounded bg-zinc-800" />
          </div>
        ))}
      </section>
      <section className="panel mt-6 h-80 animate-pulse" />
    </div>
  );
}
