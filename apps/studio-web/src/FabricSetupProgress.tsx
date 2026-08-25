export interface FabricSetupProgressStep {
  label: string;
  targetId: string;
}

export function FabricSetupProgress({
  ariaLabel,
  currentStep,
  steps,
}: {
  ariaLabel: string;
  currentStep: number;
  steps: ReadonlyArray<FabricSetupProgressStep>;
}) {
  return (
    <nav className="fabric-setup-progress" aria-label={ariaLabel}>
      <ol className="fabric-steps">
        {steps.map(({ label, targetId }, index) => {
          const step = index + 1;
          const state =
            step < currentStep
              ? "is-complete"
              : step === currentStep
                ? "is-current"
                : undefined;

          return (
            <li className={state} key={targetId}>
              <a
                href={`#${targetId}`}
                aria-current={step === currentStep ? "step" : undefined}
              >
                <span aria-hidden="true">
                  {step < currentStep ? "✓" : step}
                </span>
                <strong>{label}</strong>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
