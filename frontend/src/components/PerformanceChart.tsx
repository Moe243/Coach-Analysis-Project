import type { QbPae } from "../api/contracts";
import { signed } from "../lib/format";

const WIDTH = 760;
const HEIGHT = 255;
const PAD = 34;

export function PerformanceChart({ rows }: { rows: QbPae[] }) {
  const duplicateSeasons = new Set(
    rows
      .filter(
        (row, index) =>
          rows.findIndex((candidate) => candidate.season === row.season) !==
          index,
      )
      .map((row) => row.season),
  );
  const ordered = [...rows].sort(
    (a, b) => a.season - b.season || a.team_id.localeCompare(b.team_id),
  );
  if (!ordered.length) return null;
  const values = ordered.flatMap((row) => [
    row.actual_epa_per_dropback,
    row.expected_epa_per_dropback,
  ]);
  const floor = Math.min(-0.1, ...values);
  const ceiling = Math.max(0.25, ...values);
  const x = (index: number) =>
    ordered.length === 1
      ? WIDTH / 2
      : PAD + (index * (WIDTH - PAD * 2)) / (ordered.length - 1);
  const y = (value: number) =>
    PAD + ((ceiling - value) * (HEIGHT - PAD * 2)) / (ceiling - floor || 1);
  const path = (
    field: "actual_epa_per_dropback" | "expected_epa_per_dropback",
  ) =>
    ordered
      .map((row, index) => `${index ? "L" : "M"}${x(index)},${y(row[field])}`)
      .join(" ");

  return (
    <div className="chart-wrap">
      <div className="chart-legend" aria-hidden="true">
        <span>
          <i className="legend-actual" /> Actual
        </span>
        <span>
          <i className="legend-expected" /> Expected
        </span>
      </div>
      <svg
        className="performance-chart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Actual and expected EPA per dropback by season"
      >
        <line
          x1={PAD}
          x2={WIDTH - PAD}
          y1={y(0)}
          y2={y(0)}
          className="chart-zero"
        />
        <path
          d={path("expected_epa_per_dropback")}
          className="chart-line chart-expected"
        />
        <path
          d={path("actual_epa_per_dropback")}
          className="chart-line chart-actual"
        />
        {ordered.map((row, index) => (
          <g key={`${row.season}-${row.team_id}`}>
            <circle
              cx={x(index)}
              cy={y(row.actual_epa_per_dropback)}
              r="4.5"
              className="chart-dot actual-dot"
            >
              <title>{`${row.season} actual ${signed(row.actual_epa_per_dropback)}`}</title>
            </circle>
            <circle
              cx={x(index)}
              cy={y(row.expected_epa_per_dropback)}
              r="4"
              className="chart-dot expected-dot"
            >
              <title>{`${row.season} expected ${signed(row.expected_epa_per_dropback)}`}</title>
            </circle>
            <text x={x(index)} y={HEIGHT - 8} textAnchor="middle">
              {duplicateSeasons.has(row.season)
                ? `${row.season} ${row.team_id.replace("team_", "").toUpperCase()}`
                : row.season}
            </text>
          </g>
        ))}
      </svg>
      <table className="sr-only">
        <caption>Actual and expected EPA per dropback data</caption>
        <thead>
          <tr>
            <th>Season</th>
            <th>Actual</th>
            <th>Expected</th>
            <th>PAE</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((row) => (
            <tr key={`${row.season}-${row.team_id}`}>
              <td>{row.season}</td>
              <td>{row.actual_epa_per_dropback}</td>
              <td>{row.expected_epa_per_dropback}</td>
              <td>{row.performance_above_expectation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
