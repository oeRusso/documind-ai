/**
 * Honeypot (ADR 0005): a field people never see, so they leave it empty. Bots that fill every
 * input fill this one too, and the API rejects the sign-up.
 */
export function Honeypot() {
  return (
    <div aria-hidden="true" className="absolute -left-[10000px] h-px w-px overflow-hidden">
      <label htmlFor="website">Sitio web</label>
      <input id="website" name="website" type="text" tabIndex={-1} autoComplete="off" />
    </div>
  );
}
