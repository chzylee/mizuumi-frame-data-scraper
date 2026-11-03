export function Navbar(props: {
  showDiffs: boolean;
  onShowDiffs: (on: boolean) => void;
  scrapedAvailable: boolean;
  pending: number;
  canSave: boolean;
  onSave: () => void;
}) {
  const { showDiffs, onShowDiffs, scrapedAvailable, pending, canSave, onSave } = props;
  return (
    <header className="navbar">
      <h1 className="title">MBAACC Frame Data</h1>
      <label className={`toggle${scrapedAvailable ? "" : " disabled"}`}>
        <input
          type="checkbox"
          role="switch"
          checked={showDiffs}
          disabled={!scrapedAvailable}
          onChange={(e) => onShowDiffs(e.target.checked)}
        />
        <span className="track" aria-hidden="true" />
        Show diffs
      </label>
      {!scrapedAvailable && (
        <span className="nav-note">
          No scrape to compare. Run <code>python main.py</code> from <code>src</code>, then reload.
        </span>
      )}
      {showDiffs && (
        <span className="legend" aria-label="Diff colors">
          <span className="key green">matches scrape</span>
          <span className="key red">differs</span>
          <span className="key blue">only in scrape (preview, not saved)</span>
        </span>
      )}
      <span className="spacer" />
      {canSave && (
        <button className="primary" disabled={pending === 0} onClick={onSave}>
          Save edits{pending > 0 && <span className="count">{pending}</span>}
        </button>
      )}
    </header>
  );
}
