// Choose a new password from an emailed link. The token is in the #fragment,
// which browsers never send to servers; it's read once and removed from the
// address bar so it doesn't linger in history.
// Swayam Shakya

import { api, ApiError, session } from "../api.js";
import { clearFieldErrors, withBusy } from "../ui.js";
import { handleAuthError, notice, setupAuthPage } from "./auth-common.js";

setupAuthPage();

const token = new URLSearchParams(location.hash.slice(1)).get("token") || "";
history.replaceState(null, "", location.pathname);

const form = document.querySelector("[data-auth-form]");
if (!/^[A-Za-z0-9_-]{20,100}$/.test(token)) {
  notice("This link isn't complete. Open the link from the email again, or ask for a new one.");
  form.querySelector('[type="submit"]').disabled = true;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearFieldErrors(form);
  notice("");
  const password = form.password.value;
  if (!password) {
    handleAuthError(form, new ApiError("", { code: "validation_error", details: { password: "Enter a new password." } }));
    return;
  }
  const button = form.querySelector('[type="submit"]');
  try {
    await withBusy(button, () => api.auth.reset(token, password), "Saving…");
    session.clear();
    location.replace("login.html?reason=password_reset");
  } catch (err) {
    handleAuthError(form, err);
  }
});
