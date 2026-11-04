import { api, ApiError, session } from "../api.js";
import { clearFieldErrors, withBusy } from "../ui.js";
import { handleAuthError, notice, safeNext, setupAuthPage } from "./auth-common.js";

setupAuthPage();

if (session.isSignedIn) {
  location.replace(safeNext());
}

const reason = new URLSearchParams(location.search).get("reason");
if (reason === "expired") notice("Your session ended. Sign in again to carry on.", "warn");
if (reason === "signed_out") notice("You're signed out.", "success");
if (reason === "password_reset") notice("Password changed. Sign in with your new password.", "success");
if (reason === "deleted") notice("Your account and everything in it has been deleted.", "success");

const form = document.querySelector("[data-auth-form]");
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearFieldErrors(form);
  notice("");

  const email = form.email.value.trim();
  const password = form.password.value;
  const missing = {};
  if (!email) missing.email = "Enter your email.";
  if (!password) missing.password = "Enter your password.";
  if (Object.keys(missing).length) {
    handleAuthError(form, new ApiError("", { code: "validation_error", details: missing }));
    return;
  }

  const button = form.querySelector('[type="submit"]');
  try {
    const res = await withBusy(button, () => api.auth.login({ email, password, remember: form.remember.checked }), "Signing in…");
    session.save(res.token, form.remember.checked);
    location.replace(safeNext());
  } catch (err) {
    handleAuthError(form, err);
  }
});
