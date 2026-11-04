import { api, ApiError, session } from "../api.js";
import { clearFieldErrors, withBusy } from "../ui.js";
import { handleAuthError, notice, setupAuthPage } from "./auth-common.js";

setupAuthPage();

if (session.isSignedIn) location.replace("dashboard.html");

const form = document.querySelector("[data-auth-form]");

// Same rules as the server, checked here first so people get instant feedback.
function check(values) {
  const errors = {};
  if (!values.display_name) errors.display_name = "Tell us what to call you.";
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(values.email)) errors.email = "Enter a valid email address.";
  const pw = values.password;
  if (pw.length < 8) errors.password = "Use at least 8 characters.";
  else if (/^\d+$/.test(pw) || /^[a-z]+$/i.test(pw)) errors.password = "Mix letters with numbers or symbols.";
  return errors;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearFieldErrors(form);
  notice("");

  const values = {
    display_name: form.display_name.value.trim(),
    email: form.email.value.trim(),
    password: form.password.value,
  };
  const errors = check(values);
  if (Object.keys(errors).length) {
    const err = new ApiError("", { code: "validation_error", details: errors });
    handleAuthError(form, err);
    return;
  }

  const button = form.querySelector('[type="submit"]');
  try {
    const res = await withBusy(button, () => api.auth.register(values), "Creating your account…");
    session.save(res.token, false);
    location.replace("wardrobe.html?welcome=1");
  } catch (err) {
    handleAuthError(form, err);
  }
});
