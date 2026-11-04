// Wardrobe: list, search, filter, add, edit, archive.

import { api, ApiError, imageSrc } from "../api.js";
import { CATALOG, categoryLabel, label } from "../lib/catalog.js";
import { itemPicture } from "../outfit-view.js";
import { initShell } from "../shell.js";
import {
  clearFieldErrors, confirmDialog, debounce, demoWardrobeButton, emptyStateHTML, esc, loaderHTML,
  showFieldErrors, toast, toastError, watchApiStatus,
} from "../ui.js";

const me = await initShell("wardrobe");
if (me) start();

function start() {
  watchApiStatus();

  const state = { category: "", items: [], editing: null, counts: {} };
  const list = document.querySelector("[data-items]");
  const countEl = document.querySelector("[data-count]");
  const filters = document.querySelector("[data-filters]");
  const tabs = document.querySelector("[data-cat-tabs]");

  // ---- filter controls ----
  fillSelect(filters.season, CATALOG.seasons);
  fillSelect(filters.style, CATALOG.styles);

  function renderTabs() {
    const cats = [["", "All"], ...CATALOG.categories.map((c) => [c, categoryLabel(c, true)])];
    tabs.innerHTML = cats.map(([value, text]) =>
      `<button class="cat-tab" type="button" data-cat="${value}" aria-pressed="${state.category === value}">${text}</button>`
    ).join("");
  }
  renderTabs();
  tabs.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-cat]");
    if (!btn) return;
    state.category = btn.dataset.cat;
    renderTabs();
    load();
  });

  filters.addEventListener("change", () => load());
  filters.q.addEventListener("input", debounce(() => load(), 300));
  filters.addEventListener("reset", () => setTimeout(() => { state.category = ""; renderTabs(); load(); }));
  filters.addEventListener("submit", (e) => { e.preventDefault(); load(); });

  // ---- loading and rendering ----
  let requestNo = 0;

  async function load() {
    const mine = ++requestNo;
    const query = {
      category: state.category,
      q: filters.q.value.trim(),
      color: filters.color.value,
      season: filters.season.value,
      style: filters.style.value,
      sort: filters.sort.value,
    };
    list.setAttribute("aria-busy", "true");
    if (!state.items.length) list.innerHTML = `<div class="loading-block">${loaderHTML("Opening your wardrobe")}</div>`;
    try {
      const res = await api.wardrobe.list(query);
      if (mine !== requestNo) return; // a newer search already started
      state.items = res.items;
      refreshColourFilter(res.colors);
      render(query);
    } catch (err) {
      if (mine !== requestNo) return;
      list.innerHTML = `<div class="notice notice--error" role="alert">${esc(err.message || "Couldn't load your wardrobe.")}</div>`;
      countEl.textContent = "";
    } finally {
      list.removeAttribute("aria-busy");
    }
  }

  function refreshColourFilter(colors) {
    const current = filters.color.value;
    filters.color.innerHTML = `<option value="">Any colour</option>` +
      colors.map((c) => `<option value="${esc(c.name)}">${esc(label(c.name))} (${c.count})</option>`).join("");
    if (colors.some((c) => c.name === current)) filters.color.value = current;
  }

  function filtered(query) {
    return Boolean(query.category || query.q || query.color || query.season || query.style);
  }

  function render(query) {
    const n = state.items.length;
    countEl.textContent = n === 1 ? "1 piece" : `${n} pieces`;

    if (!n) {
      list.innerHTML = filtered(query)
        ? emptyStateHTML({ title: "Nothing matches", body: "Try a different search or clear the filters." })
        : emptyStateHTML({
            title: "Your rail is empty",
            body: "Add a few pieces to start: at least one top, one bottom (or a dress) and one pair of shoes.",
          });
      if (!filtered(query)) {
        const btn = document.createElement("button");
        btn.className = "btn btn--primary";
        btn.type = "button";
        btn.textContent = "Add your first piece";
        btn.addEventListener("click", () => openForm());
        const row = document.createElement("div");
        row.className = "empty-state__actions";
        row.append(btn, demoWardrobeButton(() => location.reload()));
        list.querySelector(".empty-state").append(row);
      }
      return;
    }

    list.innerHTML = `<ul class="item-grid">${state.items.map(cardHTML).join("")}</ul>`;
  }

  function cardHTML(item) {
    const occasions = item.occasions.slice(0, 3).map((o) => `<span class="tag-mini">${esc(label(o))}</span>`).join("");
    const more = item.occasions.length > 3 ? `<span class="tag-mini">+${item.occasions.length - 3}</span>` : "";
    return `<li class="swing-tag item-card" data-id="${Number(item.id)}">
      ${itemPicture(item)}
      <span class="swing-tag__name">${esc(item.name)}</span>
      <span class="swing-tag__meta">
        <span class="chip-dot" style="background:${esc(item.main_color.hex)}"></span>${esc(item.main_color.name)}
        ${item.secondary_color ? `+ <span class="chip-dot" style="background:${esc(item.secondary_color.hex)}"></span>${esc(item.secondary_color.name)}` : ""}
        · ${esc(item.subcategory)}
      </span>
      <div class="item-card__tags">${occasions}${more}</div>
      <div class="item-card__actions">
        <button class="btn btn--sm" type="button" data-edit aria-label="Edit ${esc(item.name)}">Edit</button>
        <button class="btn btn--sm btn--quiet" type="button" data-delete aria-label="Remove ${esc(item.name)}">Remove</button>
      </div>
    </li>`;
  }

  list.addEventListener("click", async (e) => {
    const card = e.target.closest("[data-id]");
    if (!card) return;
    const item = state.items.find((i) => i.id === Number(card.dataset.id));
    if (!item) return;

    if (e.target.closest("[data-edit]")) openForm(item);

    if (e.target.closest("[data-delete]")) {
      const ok = await confirmDialog({
        title: `Remove ${item.name}?`,
        body: "It won't be suggested any more. Outfits you've already had that used it stay in your history.",
        confirmLabel: "Remove",
        danger: true,
      });
      if (!ok) return;
      try {
        await api.wardrobe.remove(item.id);
        toast(`${item.name} removed from your wardrobe.`, "success");
        load();
      } catch (err) {
        toastError(err);
      }
    }
  });

  // ---- add / edit dialog ----
  const dialog = document.getElementById("item-dialog");
  const form = dialog.querySelector("form");
  const title = dialog.querySelector("#item-dialog-title");
  const submitBtn = dialog.querySelector("[data-submit]");
  const fileInput = form.querySelector('input[type="file"]');
  const preview = form.querySelector("[data-preview]");
  const removePhotoBtn = form.querySelector("[data-remove-photo]");
  const dropzone = form.querySelector("[data-dropzone]");
  let removePhoto = false;
  let previewUrl = null;

  buildFormControls();

  function buildFormControls() {
    form.querySelector("[data-category-chips]").innerHTML = CATALOG.categories.map((c) =>
      `<label class="chip"><input type="radio" name="category" value="${c}" required><span>${categoryLabel(c)}</span></label>`
    ).join("");
    form.querySelector("[data-season-chips]").innerHTML = CATALOG.seasons.map((s) =>
      `<label class="chip"><input type="checkbox" name="seasons" value="${s}"><span>${label(s)}</span></label>`
    ).join("") + `<button class="btn btn--sm btn--quiet" type="button" data-all-seasons>All year</button>`;
    form.querySelector("[data-occasion-chips]").innerHTML = CATALOG.occasions.map((o) =>
      `<label class="chip"><input type="checkbox" name="occasions" value="${o}"><span>${label(o)}</span></label>`
    ).join("");
    form.style.innerHTML = `<option value="">Choose a style</option>` +
      CATALOG.styles.map((s) => `<option value="${s}">${label(s)}</option>`).join("");

    const swatch = (name, value, hex, title) =>
      `<label class="swatch-opt" title="${esc(title)}"><input type="radio" name="${name}" value="${value}"
         aria-label="${esc(title)}"><span style="--sw:${hex}"></span></label>`;
    form.querySelector('[data-swatches="main_color"]').innerHTML =
      Object.entries(CATALOG.colors).map(([n, hex]) => swatch("main_color", hex, hex, label(n))).join("") +
      `<label class="swatch-opt" title="Custom colour" hidden data-custom-swatch><input type="radio" name="main_color" value="" aria-label="Custom colour"><span style="--sw:#7a86a3"></span></label>`;
    form.querySelector('[data-swatches="secondary_color"]').innerHTML =
      `<label class="swatch-opt" title="None"><input type="radio" name="secondary_color" value="" aria-label="No second colour" checked><span style="--sw:transparent;border-style:dashed"></span></label>` +
      Object.entries(CATALOG.colors).map(([n, hex]) => swatch("secondary_color", hex, hex, label(n))).join("");

    form.addEventListener("change", (e) => {
      if (e.target.name === "category") updateSubOptions(e.target.value);
    });
    form.querySelector("[data-all-seasons]").addEventListener("click", () => {
      form.querySelectorAll('[name="seasons"]').forEach((c) => (c.checked = true));
    });

    const custom = form.querySelector('[data-custom-colour="main_color"]');
    custom.addEventListener("input", () => {
      const opt = form.querySelector("[data-custom-swatch]");
      opt.hidden = false;
      opt.querySelector("input").value = custom.value;
      opt.querySelector("span").style.setProperty("--sw", custom.value);
      opt.querySelector("input").checked = true;
    });

    fileInput.addEventListener("change", () => acceptFile(fileInput.files[0]));
    removePhotoBtn.addEventListener("click", () => {
      fileInput.value = "";
      removePhoto = Boolean(state.editing?.image_url);
      showPreview(null);
    });
    ["dragenter", "dragover"].forEach((ev) => dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.add("is-over");
    }));
    ["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, () => dropzone.classList.remove("is-over")));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (!file) return;
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      acceptFile(file);
    });

    dialog.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => dialog.close()));
    dialog.addEventListener("close", () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    });
  }

  function updateSubOptions(category) {
    document.getElementById("sub-options").innerHTML =
      (CATALOG.subcategories[category] || []).map((s) => `<option value="${esc(s)}">`).join("");
  }

  // Phone photos are often 4000px and 5+ MB. Shrink big ones in the browser
  // so uploads are quick and stay under the server's limit.
  async function shrinkIfLarge(file) {
    const MAX_SIDE = 1600;
    if (file.size <= 2 * 1024 * 1024 && file.type !== "image/png") {
      const probe = await createImageBitmap(file).catch(() => null);
      if (!probe || Math.max(probe.width, probe.height) <= MAX_SIDE) { probe?.close(); return file; }
      probe.close();
    }
    let bitmap;
    try {
      bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch {
      return file; // let the server decide; it validates everything anyway
    }
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size <= 2 * 1024 * 1024) { bitmap.close(); return file; }
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const g = canvas.getContext("2d");
    g.fillStyle = "#ffffff"; // transparent PNGs get a white background rather than black
    g.fillRect(0, 0, canvas.width, canvas.height);
    g.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    if (!blob) return file;
    return new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
  }

  async function acceptFile(file) {
    if (!file) return;
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
      toast("Use a JPG, PNG or WebP image.", "error");
      fileInput.value = "";
      return showPreview(null);
    }
    const ready = await shrinkIfLarge(file);
    if (ready.size > 5 * 1024 * 1024) {
      toast("That photo is over 5 MB even after shrinking. Try a smaller one.", "error");
      fileInput.value = "";
      return showPreview(null);
    }
    if (ready !== file) {
      const dt = new DataTransfer();
      dt.items.add(ready);
      fileInput.files = dt.files;
    }
    showPreview(ready);
    suggestColour(ready);
  }

  // Ask the API what colour the garment is (it ignores the background) and
  // pre-select it, unless the person has already picked one themselves.
  async function suggestColour(file) {
    const hint = form.querySelector("[data-colour-hint]");
    hint.textContent = "";
    const picked = form.querySelector('[name="main_color"]:checked');
    if (state.editing || picked) return;
    try {
      const fd = new FormData();
      fd.append("image", file);
      const res = await api.wardrobe.analyze(fd);
      if (!res.color || form.querySelector('[name="main_color"]:checked')) return;
      selectColour("main_color", res.color.hex);
      hint.textContent = `Looks ${res.color.name} to us, so we picked it. Change it if we're wrong.`;
    } catch {
      // a suggestion is a nicety; the form works without it
    }
  }

  function showPreview(file) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    if (file) {
      previewUrl = URL.createObjectURL(file);
      preview.innerHTML = `<img class="pic" src="${previewUrl}" alt="Selected photo">`;
      removePhotoBtn.hidden = false;
      removePhoto = false;
      return;
    }
    const existing = state.editing && !removePhoto ? imageSrc(state.editing.image_url) : "";
    preview.innerHTML = existing
      ? `<img class="pic" src="${esc(existing)}" alt="Current photo">`
      : `<span class="pic pic--swatch" aria-hidden="true"></span>`;
    removePhotoBtn.hidden = !existing;
  }

  function openForm(item = null) {
    state.editing = item;
    removePhoto = false;
    form.reset();
    clearFieldErrors(form);
    form.querySelector("[data-custom-swatch]").hidden = true;
    title.textContent = item ? `Edit ${item.name}` : "Add a piece";
    submitBtn.textContent = item ? "Save changes" : "Add to wardrobe";

    if (item) {
      form.name.value = item.name;
      form.querySelector(`[name="category"][value="${item.category}"]`).checked = true;
      updateSubOptions(item.category);
      form.subcategory.value = item.subcategory;
      form.style.value = item.style;
      form.description.value = item.description || "";
      item.seasons.forEach((s) => (form.querySelector(`[name="seasons"][value="${s}"]`).checked = true));
      item.occasions.forEach((o) => (form.querySelector(`[name="occasions"][value="${o}"]`).checked = true));
      selectColour("main_color", item.main_color.hex);
      selectColour("secondary_color", item.secondary_color?.hex || "");
    } else {
      updateSubOptions("");
    }
    showPreview(null);
    dialog.showModal();
    form.name.focus();
  }

  function selectColour(name, hex) {
    const match = form.querySelector(`[name="${name}"][value="${hex}"]`);
    if (match) {
      match.checked = true;
    } else if (name === "main_color" && hex) {
      const opt = form.querySelector("[data-custom-swatch]");
      opt.hidden = false;
      opt.querySelector("input").value = hex;
      opt.querySelector("input").checked = true;
      opt.querySelector("span").style.setProperty("--sw", hex);
      form.querySelector('[data-custom-colour="main_color"]').value = hex;
    }
  }

  function readForm() {
    const fd = new FormData();
    const errors = {};
    const name = form.name.value.trim();
    const category = form.querySelector('[name="category"]:checked')?.value;
    const sub = form.subcategory.value.trim();
    const main = form.querySelector('[name="main_color"]:checked')?.value;
    const seasons = [...form.querySelectorAll('[name="seasons"]:checked')].map((c) => c.value);
    const occasions = [...form.querySelectorAll('[name="occasions"]:checked')].map((c) => c.value);

    if (!name) errors.name = "Give it a name.";
    if (!category) errors.category = "Choose a category.";
    if (!sub) errors.subcategory = "Say what type of piece it is.";
    if (!form.style.value) errors.style = "Choose a style.";
    if (!main) errors.main_color = "Pick the main colour.";
    if (!seasons.length) errors.seasons = "Pick at least one season.";
    if (!occasions.length) errors.occasions = "Pick at least one occasion.";

    fd.append("name", name);
    fd.append("category", category || "");
    fd.append("subcategory", sub);
    fd.append("style", form.style.value);
    fd.append("main_color", main || "");
    fd.append("secondary_color", form.querySelector('[name="secondary_color"]:checked')?.value || "");
    seasons.forEach((s) => fd.append("seasons", s));
    occasions.forEach((o) => fd.append("occasions", o));
    fd.append("description", form.description.value.trim());
    if (fileInput.files[0]) fd.append("image", fileInput.files[0]);
    if (removePhoto) fd.append("remove_image", "true");
    return { fd, errors };
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const { fd, errors } = readForm();
    if (Object.keys(errors).length) {
      showFieldErrors(form, errors);
      return;
    }
    clearFieldErrors(form);
    submitBtn.disabled = true;
    const label0 = submitBtn.textContent;
    submitBtn.textContent = state.editing ? "Saving…" : "Adding…";
    try {
      if (state.editing) {
        await api.wardrobe.update(state.editing.id, fd);
        toast("Changes saved.", "success");
      } else {
        const res = await api.wardrobe.create(fd);
        toast(`${res.item.name} added to your wardrobe.`, "success");
      }
      dialog.close();
      load();
    } catch (err) {
      if (err instanceof ApiError && err.details) showFieldErrors(form, err.details);
      toastError(err);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = label0;
    }
  });

  document.querySelector("[data-add-item]").addEventListener("click", () => openForm());

  // ---- go ----
  load().then(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("welcome")) {
      toast(`Welcome, ${me.user.display_name}. Add a few pieces you wear a lot, or try the demo wardrobe first.`, "info", { duration: 7000 });
      history.replaceState(null, "", "wardrobe.html");
    } else if (location.hash === "#add") {
      history.replaceState(null, "", "wardrobe.html");
      openForm();
    }
  });
}

function fillSelect(select, values) {
  select.insertAdjacentHTML("beforeend", values.map((v) => `<option value="${v}">${label(v)}</option>`).join(""));
}
