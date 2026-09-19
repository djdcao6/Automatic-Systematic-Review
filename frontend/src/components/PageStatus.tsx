// A page with nothing to show yet: loading, or the reason it could not load.
// It keeps the page's own <main> and width, so the landmark and the layout do
// not jump when the real page arrives.
export function PageStatus({ error }: { error?: string | null }) {
  return (
    <main className="page">
      {error ? <p role="alert">{error}</p> : <p className="meta">Loading...</p>}
    </main>
  );
}
