// Forgot password: asks the server to email a one-time link. The answer is the
// same whether or not the email has an account, so nobody can probe for accounts.
// Swayam Shakya

import { api, ApiError } from "../api.js";
import { clearFieldErrors, withBusy } from "../ui.js";
import { handleAuthError, notice, setupAuthPage } from "./auth-common.js";

setupAuthPage();

const form = document.querySelector("[data-auth-form]");
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearFieldErrors(form);
  notice("");
  const email = form.email.value.trim();
  if (!email) {
    handleAuthError(form, new ApiError("", { code: "validation_error", details: { email: "Enter your email." } }));
    return;
  }
  const button = form.querySelector('[type="submit"]');
  try {
    const res = await withBusy(button, () => api.auth.forgot(email), "Sending…");
    notice(res.message, "success");
    form.email.value = "";
  } catch (err) {
    handleAuthError(form, err);
  }
});
