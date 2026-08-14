"use client";

import { useState } from "react";

const runs = {
  completed: {
    label: "Evidence-satisfied run",
    status: "Completed",
    statusClass: "completed",
    run: "run-aff7c38b12c1",
    headline: "A bounded option satisfies every declared hard constraint.",
    result: "plan-25025000202-25025000502",
    metrics: [
      ["Combinations evaluated", "55"],
      ["Feasible combinations", "16"],
      ["Estimated proxy covered", "3,121.507"],
      ["Overall coverage rate", "96.35%"],
    ],
    note: "Five service-radius tests produced three different selected bounded options, making the result visibly assumption-sensitive.",
  },
  infeasible: {
    label: "Deliberately infeasible run",
    status: "Infeasible",
    statusClass: "withheld",
    run: "run-8a6e1c70ae7a",
    headline: "No candidate combination satisfies every declared hard constraint.",
    result: "Recommendation withheld",
    metrics: [
      ["Combinations evaluated", "10"],
      ["Feasible combinations", "0"],
      ["Declared service radius", "0.00 km"],
      ["Selected option", "None"],
    ],
    note: "The system preserves the failure reason and evidence gaps instead of manufacturing a recommendation.",
  },
} as const;

type RunName = keyof typeof runs;

export function CaseStudy() {
  const [selected, setSelected] = useState<RunName>("completed");
  const run = runs[selected];

  return (
    <div className="case-workspace">
      <div className="case-tabs" role="tablist" aria-label="Reference case runs">
        {(Object.keys(runs) as RunName[]).map((key) => (
          <button
            aria-controls="case-panel"
            aria-selected={selected === key}
            className={selected === key ? "active" : ""}
            key={key}
            onClick={() => setSelected(key)}
            role="tab"
            type="button"
          >
            <span>{key === "completed" ? "01" : "02"}</span>{runs[key].label}
          </button>
        ))}
      </div>
      <article className="case-panel" id="case-panel" role="tabpanel" aria-live="polite">
        <div className="case-panel-head">
          <div><p>Reference DecisionPack</p><h3>{run.headline}</h3></div>
          <span className={`case-status ${run.statusClass}`}>{run.status}</span>
        </div>
        <div className="case-run"><span>Run</span><code>{run.run}</code></div>
        <div className="case-result"><span>Result</span><strong>{run.result}</strong></div>
        <div className="case-metrics">
          {run.metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
        </div>
        <p className="case-note"><span aria-hidden="true">↳</span>{run.note}</p>
      </article>
    </div>
  );
}
