import { CaseStudy } from "./case-study";

const repository = "https://github.com/limingrui679-design/civicdecision-os";

const evidenceTypes = [
  ["Observed", "10 parsed public-data rows in the bounded reference sample."],
  ["Estimated", "3,239.695 people represented by an area-level need proxy."],
  ["Simulated", "Straight-line coverage around tract-centroid candidates."],
  ["Optimized", "55 bounded combinations evaluated against declared constraints."],
  ["Proposed", "Candidate points are demonstrations—not verified facilities."],
] as const;

const steps = [
  ["01", "Type the evidence", "Keep observed, estimated, simulated, optimized, and proposed claims separate."],
  ["02", "Run the decision", "Replay, simulate, and optimize within explicit data and method gates."],
  ["03", "Test reversals", "Show which assumptions can change the selected bounded option."],
  ["04", "Release or withhold", "Emit a DecisionPack—or preserve an auditable negative result."],
] as const;

export default function Home() {
  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="CivicDecision OS home">
          <span className="brand-mark" aria-hidden="true"><i /></span>
          <span><strong>CivicDecision</strong><small>Evidence OS</small></span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#proof">Proof</a>
          <a href="#case">Walkthrough</a>
          <a href="#boundaries">Boundaries</a>
          <a href="#start">Start</a>
        </nav>
        <a className="header-link" href={repository}>GitHub <span aria-hidden="true">↗</span></a>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow"><span>Public evidence</span><span>Versioned methods</span><span>Auditable decisions</span></p>
          <h1>Urban decisions,<br /><em>with an evidence trail.</em></h1>
          <p className="hero-lede">
            Build reproducible urban intervention analyses that expose the evidence,
            assumptions, uncertainty—and when no recommendation is justified.
          </p>
          <div className="hero-actions">
            <a className="button primary" href="#case">Walk through one case</a>
            <a className="button quiet" href={`${repository}#five-minute-quickstart`}>Run it locally <span aria-hidden="true">↘</span></a>
          </div>
          <div className="snapshot-stamp">
            <span><i className="status-dot" /> Read-only public walkthrough</span>
            <span>Verified release snapshot · v0.8.1</span>
          </div>
        </div>

        <div className="hero-visual" aria-label="Evidence gate overview">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="network-lines" aria-hidden="true">
            <i /><i /><i /><i /><i /><i /><i />
          </div>
          <article className="signal-card signal-primary">
            <span>Deep evidence gate</span>
            <strong>76 / 96</strong>
            <small>completed · 20 withheld</small>
          </article>
          <article className="signal-card signal-secondary">
            <span>Catalog</span>
            <strong>258</strong>
            <small>highest-available city records</small>
          </article>
          <p className="visual-caption"><span>G</span> discovery <span>S</span> screening <span>D</span> deep evidence</p>
        </div>
      </section>

      <section className="proof-band" id="proof" aria-label="Verified repository snapshot">
        <article><strong>258</strong><span>city records</span><small>highest available tier</small></article>
        <article><strong>240</strong><span>scenario designs</span><small>30 × 8 audited matrix</small></article>
        <article><strong>98</strong><span>DecisionPacks</span><small>including negative releases</small></article>
        <article><strong>800</strong><span>passing tests</span><small>implementation behavior</small></article>
      </section>

      <aside className="boundary-ribbon">
        <span aria-hidden="true">i</span>
        <p><strong>Evidence boundary:</strong> public-data analysis and reproducibility are not deployment, adoption, external validation, causal impact, or a municipal recommendation.</p>
        <a href="#boundaries">Read the boundaries</a>
      </aside>

      <section className="section process" aria-labelledby="process-title">
        <div className="section-heading">
          <div><p className="section-kicker">From evidence to release</p><h2 id="process-title">One traceable path.<br /><em>Five evidence types.</em></h2></div>
          <p>CivicDecision OS is built for urban analysts and civic data teams who need a reviewable record of how an intervention screen reached—or refused—a result.</p>
        </div>
        <div className="step-grid">
          {steps.map(([number, title, body]) => (
            <article key={number}><span>{number}</span><h3>{title}</h3><p>{body}</p></article>
          ))}
        </div>
      </section>

      <section className="case-section" id="case" aria-labelledby="case-title">
        <div className="section case-shell">
          <div className="section-heading inverse">
            <div><p className="section-kicker">Guided reference case</p><h2 id="case-title">Suffolk heat access.<br /><em>Including the right to say no.</em></h2></div>
            <p>Two deterministic runs use the same bounded public-data sample: one satisfies the declared constraints; one deliberately makes the candidate set infeasible.</p>
          </div>
          <CaseStudy />
          <div className="evidence-stack" aria-label="Evidence layers in the reference case">
            {evidenceTypes.map(([type, description]) => (
              <article key={type}><span>{type}</span><p>{description}</p></article>
            ))}
          </div>
          <p className="case-footnote">
            Tract centroids are not verified facilities; straight-line radius is not travel time; the population proxy is not individual demand. The selected bounded option is a methods result, not an implementation recommendation.
          </p>
        </div>
      </section>

      <section className="section boundaries" id="boundaries" aria-labelledby="boundary-title">
        <div className="section-heading">
          <div><p className="section-kicker">Fail-closed by design</p><h2 id="boundary-title">What the system<br /><em>refuses to overclaim.</em></h2></div>
          <p>A valid output can be completed, infeasible, or insufficient-evidence. Negative evidence is retained instead of being hidden.</p>
        </div>
        <div className="boundary-grid">
          <article><span>01</span><h3>Simulation ≠ observed impact</h3><p>Modeled draws remain conditional on the declared inputs and assumptions.</p></article>
          <article><span>02</span><h3>Optimization ≠ adoption</h3><p>A selected bounded option does not prove institutional approval or implementation.</p></article>
          <article><span>03</span><h3>Coverage ≠ readiness</h3><p>A city point or public-data screen does not establish a local intervention evidence base.</p></article>
          <article><span>04</span><h3>Tests ≠ policy validity</h3><p>Software verification establishes implementation behavior, not real-world effectiveness.</p></article>
        </div>
      </section>

      <section className="start-section" id="start" aria-labelledby="start-title">
        <div className="start-copy">
          <p className="section-kicker">Five-minute quickstart</p>
          <h2 id="start-title">Inspect the method.<br /><em>Reproduce the artifact.</em></h2>
          <p>Install the repository, open the full local Evidence Explorer, or reproduce the bounded heat-access DecisionPack from committed inputs.</p>
          <div className="start-links">
            <a className="button primary" href={`${repository}#five-minute-quickstart`}>Open quickstart</a>
            <a className="button quiet" href={`${repository}/blob/main/examples/outputs/suffolk-heat-access/decision-brief.md`}>Read the DecisionPack brief</a>
          </div>
        </div>
        <div className="terminal" aria-label="Installation commands">
          <div className="terminal-head"><span /><span /><span /><small>local terminal</small></div>
          <pre><code>{`git clone ${repository}.git\ncd civicdecision-os\npython -m venv .venv\n. .venv/bin/activate\npython -m pip install -e '.[api]'\ncivicdecision serve --root .`}</code></pre>
          <p>Then open <strong>http://127.0.0.1:8000</strong></p>
        </div>
      </section>

      <footer>
        <div className="brand footer-brand"><span className="brand-mark" aria-hidden="true"><i /></span><span><strong>CivicDecision</strong><small>Evidence OS · v0.8.1</small></span></div>
        <p>Public-data reference implementation. No deployment, adoption, external review, or real-world impact is claimed.</p>
        <nav aria-label="Footer navigation"><a href={repository}>Repository</a><a href={`${repository}/tree/main/docs`}>Documentation</a><a href={`${repository}/blob/main/LICENSE`}>MIT License</a></nav>
      </footer>
    </main>
  );
}
