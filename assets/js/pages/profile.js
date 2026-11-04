// Profile: name, preferences, password, account deletion.

import { api, ApiError, session } from "../api.js";
import { CATALOG, label, PALETTE_SWATCHES } from "../lib/catalog.js";
import { initShell } from "../shell.js";
import {
  clearFieldErrors, confirmDialog, esc, formatDate, passwordDialog, showFieldErrors, toast, toastError, watchApiStatus, withBusy,
} from "../ui.js";

const me = await initShell("profile");
if (me) start();

async function start() {
  watchApiStatus();
  const layout = document.querySelector("[data-profile]");
  const loading = document.querySelector("[data-profile-loading]");

  let profile;
  try {
    profile = await api.profile.get();
  } catch (err) {
    loading.innerHTML = `<div class="notice notice--error" role="alert">${esc(err.message)}</div>`;
    return;
  }

  const account = document.querySelector('[data-form="account"]');
  const prefsForm = document.querySelector('[data-form="preferences"]');
  const pwForm = document.querySelector('[data-form="password"]');
  const delForm = document.querySelector('[data-form="delete"]');

  // ---- build controls ----
  prefsForm.querySelector("[data-pref-styles]").innerHTML = CATALOG.styles.map((s) =>
    `<label class="chip"><input type="checkbox" name="preferred_styles" value="${s}"><span>${label(s)}</span></label>`).join("");
  prefsForm.querySelector("[data-pref-palette]").innerHTML = CATALOG.palettes.map((p) => {
    const sw = PALETTE_SWATCHES[p].map((h) => `<i style="background:${h}"></i>`).join("");
    return `<label class="chip"><input type="radio" name="preferred_palette" value="${p}">
      <span>${sw ? `<span class="mini-swatches" aria-hidden="true">${sw}</span>` : ""}${p === "any" ? "No preference" : label(p)}</span></label>`;
  }).join("");
  const swatchBoxes = (name) => Object.entries(CATALOG.colors).map(([n, hex]) =>
    `<label class="swatch-opt" title="${esc(label(n))}"><input type="checkbox" name="${name}" value="${esc(n)}" aria-label="${esc(label(n))}"><span style="--sw:${hex}"></span></label>`).join("");
  prefsForm.querySelector("[data-pref-fav]").innerHTML = swatchBoxes("favorite_colors");
  prefsForm.querySelector("[data-pref-avoid]").innerHTML = swatchBoxes("avoided_colors");
  prefsForm.default_occasion.insertAdjacentHTML("beforeend",
    CATALOG.occasions.map((o) => `<option value="${o}">${label(o)}</option>`).join(""));

  // a colour can't be both a favourite and avoided: ticking one unticks the other
  prefsForm.addEventListener("change", (e) => {
    const other = { favorite_colors: "avoided_colors", avoided_colors: "favorite_colors" }[e.target.name];
    if (other && e.target.checked) {
      const twin = prefsForm.querySelector(`[name="${other}"][value="${CSS.escape(e.target.value)}"]`);
      if (twin) twin.checked = false;
    }
  });

  function fill(p) {
    account.display_name.value = p.user.display_name;
    document.getElementById("p-email").value = p.user.email;
    document.querySelector("[data-member-since]").textContent =
      `Member since ${new Date(/[zZ]|[+-]\d\d:\d\d$/.test(p.user.created_at) ? p.user.created_at : p.user.created_at + "Z").toLocaleDateString([], { month: "long", year: "numeric" })}. ` +
      `${p.stats.items} pieces, ${p.stats.outfits} outfits.`;
    const pr = p.preferences;
    prefsForm.querySelectorAll('[name="preferred_styles"]').forEach((c) => (c.checked = pr.preferred_styles.includes(c.value)));
    const pal = prefsForm.querySelector(`[name="preferred_palette"][value="${pr.preferred_palette}"]`);
    if (pal) pal.checked = true;
    prefsForm.querySelectorAll('[name="favorite_colors"]').forEach((c) => (c.checked = pr.favorite_colors.includes(c.value)));
    prefsForm.querySelectorAll('[name="avoided_colors"]').forEach((c) => (c.checked = pr.avoided_colors.includes(c.value)));
    prefsForm.default_occasion.value = pr.default_occasion || "";
    prefsForm.temperature_unit.value = pr.temperature_unit;
    prefsForm.budget.value = pr.budget || "budget";
    for (const k of ["model_build", "model_skin", "model_body", "photo_setting"]) {
      const r = prefsForm.querySelector(`[name="${k}"][value="${pr[k]}"]`);
      if (r) r.checked = true;
    }
  }
  fill(profile);
  loading.hidden = true;
  layout.hidden = false;

  async function submit(form, body, success) {
    clearFieldErrors(form);
    const btn = form.querySelector('[type="submit"]');
    try {
      profile = await withBusy(btn, () => api.profile.update(body), "Saving…");
      toast(success, "success");
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.details) showFieldErrors(form, err.details);
      toastError(err);
      return false;
    }
  }

  account.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = account.display_name.value.trim();
    if (!name) return showFieldErrors(account, { display_name: "Name can't be empty." });
    if (await submit(account, { display_name: name }, "Name updated.")) {
      document.querySelector("[data-user-name]").textContent = profile.user.display_name;
    }
  });

  prefsForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const checked = (name) => [...prefsForm.querySelectorAll(`[name="${name}"]:checked`)].map((c) => c.value);
    const fav = checked("favorite_colors");
    const avoid = checked("avoided_colors");
    if (fav.length > 8 || avoid.length > 8) {
      return showFieldErrors(prefsForm, {
        ...(fav.length > 8 ? { favorite_colors: "Pick at most 8." } : {}),
        ...(avoid.length > 8 ? { avoided_colors: "Pick at most 8." } : {}),
      });
    }
    await submit(prefsForm, {
      preferences: {
        preferred_styles: checked("preferred_styles"),
        preferred_palette: prefsForm.querySelector('[name="preferred_palette"]:checked')?.value || "any",
        favorite_colors: fav,
        avoided_colors: avoid,
        default_occasion: prefsForm.default_occasion.value || null,
        temperature_unit: prefsForm.temperature_unit.value,
        budget: prefsForm.budget.value,
        model_build: prefsForm.querySelector('[name="model_build"]:checked')?.value || "masc",
        model_skin: prefsForm.querySelector('[name="model_skin"]:checked')?.value || "medium",
        model_body: prefsForm.querySelector('[name="model_body"]:checked')?.value || "average",
        photo_setting: prefsForm.querySelector('[name="photo_setting"]:checked')?.value || "studio",
      },
    }, "Preferences saved. They apply to your next outfit.");
  });

  pwForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const current = pwForm.current_password.value;
    const next = pwForm.new_password.value;
    const errors = {};
    if (!current) errors.current_password = "Enter your current password.";
    if (next.length < 8) errors.new_password = "Use at least 8 characters.";
    if (Object.keys(errors).length) return showFieldErrors(pwForm, errors);
    if (await submit(pwForm, { current_password: current, new_password: next }, "Password changed. Other devices have been signed out.")) {
      pwForm.reset();
    }
  });

  // ---- realistic photos: engine and keys ----
  const photoForm = document.querySelector('[data-form="photos"]');
  const pollenForm = document.querySelector('[data-form="pollen"]');
  const photoStatusEl = document.querySelector("[data-photo-status]");
  const removeKey = document.querySelector("[data-photo-remove]");
  const removePollen = document.querySelector("[data-pollen-remove]");
  const engineRadios = document.querySelectorAll('[name="engine"]');
  let photoState = null;
  function showPhotoStatus(st, chosen = st.engine) {
    photoState = st;
    engineRadios.forEach((r) => (r.checked = r.value === chosen));
    photoForm.hidden = chosen !== "gemini";
    pollenForm.hidden = chosen !== "free";
    photoStatusEl.innerHTML = st.engine === "gemini"
      ? `<span class="status-dot status-dot--on"></span> Using <strong>Google Gemini</strong> (${esc(st.gemini.model)}, key ending <strong>${esc(st.gemini.hint)}</strong>).`
      : `<span class="status-dot status-dot--on"></span> Using the <strong>free open-source engine</strong>, ${st.free.key_hint
        ? `with your Pollinations key ending <strong>${esc(st.free.key_hint)}</strong>.` : "with no account."}`;
    removeKey.hidden = !st.gemini.configured;
    removePollen.hidden = !st.free.key_hint;
  }
  let picked = null;    // a choice made before the status arrived wins
  api.photos.status().then((st) => {
    const early = [...engineRadios].find((r) => r.checked)?.value;   // ticked before this script was ready
    showPhotoStatus(st, picked || early || st.engine);
  }).catch(() => {});
  engineRadios.forEach((r) => r.addEventListener("change", async () => {
    picked = r.value;
    if (!photoState) { photoForm.hidden = r.value !== "gemini"; pollenForm.hidden = r.value !== "free"; return; }
    if (r.value === "free") {
      showPhotoStatus(await api.photos.useFree(), "free");
      toast("Using the free open-source photo engine.", "success");
    } else if (photoState?.gemini.configured) {
      showPhotoStatus(await api.photos.useGemini());
      toast("Using Google Gemini for photos.", "success");
    } else {
      showPhotoStatus(photoState, "gemini");      // show the key form; switches once a key is saved
      photoForm.gemini_key.focus();
    }
  }));
  pollenForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(pollenForm);
    try {
      const st = await withBusy(pollenForm.querySelector('[type="submit"]'), () => api.photos.useFree({ key: pollenForm.pollen_key.value }), "Saving…");
      pollenForm.reset();
      showPhotoStatus(st);
      toast(st.free.key_hint ? "Free key saved. Photos will be faster and logo-free." : "Using the free engine with no account.", "success");
    } catch (err) {
      if (err instanceof ApiError && err.details) showFieldErrors(pollenForm, err.details);
      else toastError(err);
    }
  });
  removePollen.addEventListener("click", async () => {
    showPhotoStatus(await api.photos.useFree({ key: "" }));
    toast("Pollinations key removed.", "success");
  });
  photoForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(photoForm);
    const key = photoForm.gemini_key.value.trim();
    if (!key) return showFieldErrors(photoForm, { gemini_key: "Paste your Gemini API key." });
    try {
      const st = await withBusy(photoForm.querySelector('[type="submit"]'), () => api.photos.connect(key), "Checking with Google…");
      photoForm.reset();
      showPhotoStatus(st);
      toast("Gemini is on. Your next outfit photo will come from Gemini.", "success");
    } catch (err) {
      if (err instanceof ApiError) showFieldErrors(photoForm, { gemini_key: err.message });
      else toastError(err);
    }
  });
  removeKey.addEventListener("click", async () => {
    showPhotoStatus(await api.photos.disconnect());
    toast("Gemini key removed. Back to the free engine.", "success");
  });
  if (location.hash === "#photos") document.getElementById("photos").scrollIntoView({ block: "start" });

  // ---- sessions ----
  // ---- signed-in devices ----
  const devices = document.querySelector("[data-devices]");
  const when = (iso) => {
    const mins = Math.round((Date.now() - new Date(iso)) / 60000);
    if (mins < 2) return "active now";
    if (mins < 60) return `active ${mins} minutes ago`;
    if (mins < 1440) return `active ${Math.round(mins / 60)} hours ago`;
    return `last active ${formatDate(iso)}`;
  };
  async function loadDevices() {
    try {
      const { sessions } = await api.auth.sessions();
      devices.innerHTML = sessions.map((s) => `<li class="device">
        <span class="device__name">${esc(s.device)}${s.current ? ' <span class="tag-mini">This device</span>' : ""}</span>
        <span class="device__meta">${esc(when(s.last_seen_at))} · signed in ${esc(formatDate(s.signed_in_at))}${s.remember ? " · kept signed in" : ""}</span>
        <button class="btn btn--sm btn--quiet" type="button" data-end-session="${Number(s.id)}"
          aria-label="Sign out ${esc(s.device)}${s.current ? " (this device)" : ""}">Sign out</button>
      </li>`).join("") || '<li class="muted">No active sign-ins.</li>';
    } catch {
      devices.innerHTML = '<li class="muted">Couldn\'t load the list.</li>';
    }
  }
  devices.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-end-session]");
    if (!btn) return;
    const current = btn.closest(".device").querySelector(".tag-mini");
    try {
      await withBusy(btn, () => api.auth.endSession(btn.dataset.endSession), "…");
      if (current) {
        session.clear();
        location.href = "login.html?reason=signed_out";
        return;
      }
      toast("That device is signed out.", "success");
      loadDevices();
    } catch (err) {
      toastError(err);
    }
  });
  loadDevices();

  document.querySelector("[data-sign-out-all]")?.addEventListener("click", async () => {
    const ok = await confirmDialog({ title: "Sign out everywhere?", body: "Every device and browser signed in to this account will be signed out.", confirmLabel: "Sign out everywhere" });
    if (!ok) return;
    try { await api.auth.logoutEverywhere(); } catch { /* signed out anyway */ }
    session.clear();
    location.href = "login.html?reason=signed_out";
  });

  // ---- backup ----
  document.querySelector("[data-export]").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const pw = await passwordDialog({ title: "Download a backup", body: "The backup holds your whole wardrobe and outfit history, so it needs your password.", confirmLabel: "Download" });
    if (!pw) return;
    try {
      const data = await withBusy(btn, () => api.profile.exportData(pw), "Packing…");
      const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `fitcheck-backup-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      toast(`Backup saved: ${data.items.length} pieces, ${data.outfits.length} outfits.`, "success");
    } catch (err) {
      toastError(err, "Couldn't make the backup.");
    }
  });

  document.querySelector("[data-import]").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const ok = await confirmDialog({
      title: "Restore this backup?",
      body: "The wardrobe, outfits and preferences in this account will be replaced by the ones in the file.",
      confirmLabel: "Restore",
      danger: true,
    });
    if (!ok) return;
    try {
      let backup;
      try { backup = JSON.parse(await file.text()); } catch { throw new ApiError("That file isn't a FitCheck.AI backup.", { code: "bad_backup" }); }
      const res = await api.profile.importData(backup);
      toast(`Restored ${res.items ?? backup.items.length} pieces.`, "success");
      profile = await api.profile.get();
      fill(profile);
    } catch (err) {
      toastError(err, "Couldn't restore that backup.");
    }
  });

  delForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(delForm);
    const password = delForm.password.value;
    if (!password) return showFieldErrors(delForm, { password: "Enter your password to confirm." });
    const ok = await confirmDialog({
      title: "Delete your account?",
      body: "Your wardrobe, photos, outfits and preferences will be erased for good.",
      confirmLabel: "Delete everything",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.profile.remove(password);
      session.clear();
      location.replace("login.html?reason=deleted");
    } catch (err) {
      if (err instanceof ApiError && err.details) showFieldErrors(delForm, err.details);
      toastError(err);
    }
  });
}
