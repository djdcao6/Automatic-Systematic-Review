// The AI disclosure (#61). One sentence, shown at sign-up and, for an account that
// pre-dates it, once in AiConsentDialog. The wording lives here so both say the same.
export const AI_DISCLOSURE =
  "Abstracts, PDFs and criteria you add are sent to Anthropic's API to generate suggestions. " +
  "Don't upload patient-identifiable data.";

// The required checkbox on the two sign-up forms.
export function AiConsentField({
  id,
  checked,
  onChange,
}: {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label htmlFor={id} className="consent">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        aria-required="true"
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>I understand: {AI_DISCLOSURE}</span>
    </label>
  );
}
