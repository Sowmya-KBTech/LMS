// Small "step" strip showing how far a student got through a role's
// selection rounds. progress = application.round_progress from the API.
const LABEL = {
  cleared: "Cleared",
  not_cleared: "Not cleared",
  absent: "Absent",
  pending: "Awaiting result",
  not_reached: "—",
};

export default function RoundSteps({ progress }) {
  if (!progress || progress.length === 0) return null;
  return (
    <ol className="pl-steps" aria-label="Selection rounds">
      {progress.map((p) => (
        <li key={p.id} className={`pl-step is-${p.status}`} title={LABEL[p.status]}>
          <span className="pl-step-name">{p.name}</span>
          <span className="pl-step-state">{LABEL[p.status]}</span>
        </li>
      ))}
    </ol>
  );
}
