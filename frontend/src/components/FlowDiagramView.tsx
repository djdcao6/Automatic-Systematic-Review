import type { Criteria, FlowDiagram } from "@/lib/api";

function CriteriaHeader({ criteria }: { criteria: Criteria | null }) {
  if (!criteria) {
    return (
      <section aria-label="Review Project Criteria">
        <h2>Criteria</h2>
        <p>No Criteria saved yet for this Review Project.</p>
      </section>
    );
  }

  return (
    <section aria-label="Review Project Criteria">
      <h2>Criteria</h2>
      <dl>
        <dt>Population</dt>
        <dd>{criteria.population || "—"}</dd>
        <dt>Intervention</dt>
        <dd>{criteria.intervention || "—"}</dd>
        <dt>Comparison</dt>
        <dd>{criteria.comparison || "—"}</dd>
        <dt>Outcome</dt>
        <dd>{criteria.outcome || "—"}</dd>
        <dt>Exclusion Rules</dt>
        <dd>
          {criteria.exclusion_rules.length > 0 ? (
            <ul>
              {criteria.exclusion_rules.map((rule) => (
                <li key={rule}>{rule}</li>
              ))}
            </ul>
          ) : (
            "—"
          )}
        </dd>
      </dl>
    </section>
  );
}

function totalIdentified(diagram: FlowDiagram): number {
  return Object.values(diagram.identification_counts).reduce((sum, count) => sum + count, 0);
}

function ScreeningFunnelDiagram({ diagram }: { diagram: FlowDiagram }) {
  const sourceEntries = Object.entries(diagram.identification_counts);

  return (
    <section aria-label="Screening funnel diagram">
      <h2>Screening Funnel</h2>
      <div>
        <h3>Identification</h3>
        {sourceEntries.length > 0 ? (
          <ul>
            {sourceEntries.map(([source, count]) => (
              <li key={source}>
                {source}: {count}
              </li>
            ))}
          </ul>
        ) : (
          <p>No records identified yet.</p>
        )}
        <p>Total records identified: {totalIdentified(diagram)}</p>
      </div>
      <p aria-hidden="true">↓</p>
      <div>
        <p>Duplicates removed: {diagram.duplicates_removed}</p>
      </div>
      <p aria-hidden="true">↓</p>
      <div>
        <h3>Screened</h3>
        <p>Records screened: {diagram.screened}</p>
        <p>Records excluded: {diagram.excluded}</p>
        <p>{diagram.pending} citation(s) still pending a Screening Decision</p>
      </div>
    </section>
  );
}

function SummaryTable({ diagram }: { diagram: FlowDiagram }) {
  const sourceEntries = Object.entries(diagram.identification_counts);

  return (
    <table>
      <caption>Numeric Summary</caption>
      <tbody>
        {sourceEntries.map(([source, count]) => (
          <tr key={source}>
            <th scope="row">Identified ({source})</th>
            <td>{count}</td>
          </tr>
        ))}
        <tr>
          <th scope="row">Total Identified</th>
          <td>{totalIdentified(diagram)}</td>
        </tr>
        <tr>
          <th scope="row">Duplicates Removed</th>
          <td>{diagram.duplicates_removed}</td>
        </tr>
        <tr>
          <th scope="row">Screened</th>
          <td>{diagram.screened}</td>
        </tr>
        <tr>
          <th scope="row">Excluded</th>
          <td>{diagram.excluded}</td>
        </tr>
        <tr>
          <th scope="row">Pending Decision</th>
          <td>{diagram.pending}</td>
        </tr>
      </tbody>
    </table>
  );
}

export function FlowDiagramView({ diagram }: { diagram: FlowDiagram }) {
  return (
    <>
      <CriteriaHeader criteria={diagram.criteria} />
      <ScreeningFunnelDiagram diagram={diagram} />
      <SummaryTable diagram={diagram} />
    </>
  );
}
