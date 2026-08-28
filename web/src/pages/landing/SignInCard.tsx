import { useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { errorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import LandingIcon from "./LandingIcon";

/**
 * The sign-in card on the public landing page.
 *
 * Hand-built rather than antd's `Form`, and the reason is the accessibility
 * contract in the build prompt: errors render **next to their field**, focus
 * moves to the first invalid one on submit, the reveal toggle carries
 * `aria-pressed` at a 44px target, and nothing blocks paste. antd's Form puts
 * its own error placement and focus behaviour in the way of all four, and the
 * repo's rule is that antd keeps behaviour where the behaviour is what we
 * want — here it is not.
 *
 * Two controls the mock draws are deliberately absent. "Forgot password" has
 * no reset flow behind it and "Trust this device for 30 days" has no device
 * trust; a dead control on a sign-in page is worse than no control, because
 * the person reaching for it has already failed to get in. The help block
 * says who does issue and reset accounts instead.
 */
export default function SignInCard() {
  const { t } = useLang();
  const { login } = useAuth();
  const navigate = useNavigate();

  const ids = useId();
  const userId = `${ids}-user`;
  const passId = `${ids}-pass`;

  const userRef = useRef<HTMLInputElement>(null);
  const passRef = useRef<HTMLInputElement>(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({});
  // One message, and only for a failure the fields cannot explain — a wrong
  // password, a suspended account, the server being unreachable.
  const [formError, setFormError] = useState("");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError("");

    const next: { username?: string; password?: string } = {};
    if (!username.trim()) next.username = t("landing.usernameRequired");
    if (!password) next.password = t("landing.passwordRequired");
    setErrors(next);

    // Focus the first invalid field, in document order, so a screen-reader
    // user lands on the problem rather than on a summary that describes it.
    if (next.username) return userRef.current?.focus();
    if (next.password) return passRef.current?.focus();

    setSubmitting(true);
    try {
      await login(username.trim(), password);
      // Where each role goes is `Home`'s decision, not this card's, so it
      // hands off to the root route rather than restating the mapping.
      navigate("/", { replace: true });
    } catch (error) {
      setFormError(errorMessage(error, t("landing.failed")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="signin" id="signin" aria-labelledby={`${ids}-title`}>
      <h2 id={`${ids}-title`} className="signin__title">
        {t("landing.signInTitle")}
      </h2>
      <p className="signin__lede">{t("landing.signInLede")}</p>

      <form onSubmit={onSubmit} noValidate>
        {/* `role="alert"` rather than a status region: this only ever appears
            because a submission failed, and it must interrupt. */}
        {formError && (
          <p className="signin__formerr" role="alert">
            <LandingIcon name="megaphone" size={18} />
            <span>{formError}</span>
          </p>
        )}

        <div className="field">
          <label htmlFor={userId}>{t("landing.username")}</label>
          <input
            id={userId}
            ref={userRef}
            name="username"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            aria-invalid={errors.username ? true : undefined}
            aria-describedby={errors.username ? `${userId}-err` : undefined}
          />
          {/* No resting hint here. It read "The username your woreda FSCO
              issued", which is what the card's own lede says one line above —
              a duplicated sentence costing a line of a form that has to fit
              beside the headline. The password hint stays, because it carries
              an affordance rather than a repetition. */}
          {errors.username && (
            <p className="field__err" id={`${userId}-err`}>
              <LandingIcon name="megaphone" size={16} />
              <span>{errors.username}</span>
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor={passId}>{t("landing.password")}</label>
          <div className="field__control">
            <input
              id={passId}
              ref={passRef}
              name="password"
              // Toggled, never `onPaste={e => e.preventDefault()}`. WCAG 2.2
              // accessible authentication: blocking paste breaks password
              // managers, which is most of what makes a strong password usable.
              type={revealed ? "text" : "password"}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={errors.password ? true : undefined}
              aria-describedby={errors.password ? `${passId}-err` : `${passId}-hint`}
            />
            <button
              type="button"
              className="field__reveal"
              aria-pressed={revealed}
              aria-label={t("landing.revealLabel")}
              aria-controls={passId}
              onClick={() => {
                setRevealed((shown) => !shown);
                passRef.current?.focus();
              }}
            >
              {revealed ? t("landing.hide") : t("landing.reveal")}
            </button>
          </div>
          {errors.password ? (
            <p className="field__err" id={`${passId}-err`}>
              <LandingIcon name="megaphone" size={16} />
              <span>{errors.password}</span>
            </p>
          ) : (
            <p className="field__hint" id={`${passId}-hint`}>
              {t("landing.passwordHint")}
            </p>
          )}
        </div>

        <button className="signin__submit" type="submit" disabled={submitting}>
          {submitting ? t("landing.submitting") : t("landing.submit")}
        </button>
      </form>

      <div className="signin__help">
        <h3>{t("landing.helpTitle")}</h3>
        <p>{t("landing.helpBody")}</p>
        {/* A static file, so it opens whether or not the account does — which
            is the whole reason it is on this side of the sign-in. */}
        <a href="/manual.html" target="_blank" rel="noreferrer">
          {t("landing.manual")}
          <span className="sr-only"> {t("shell.opensNewTab")}</span>
        </a>
      </div>

      <p className="signin__note">
        <LandingIcon name="phone" size={18} />
        <span>{t("landing.mobileNote")}</span>
      </p>
    </section>
  );
}
