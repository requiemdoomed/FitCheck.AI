// Like / not-for-me / save buttons on a full outfit view. Shared by the
// generator and the single-outfit page.

import { api } from "./api.js";
import { label } from "./lib/catalog.js";
import { esc, toast, toastError } from "./ui.js";

function askName(defaultName) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "dialog dialog--small";
    dlg.innerHTML = `
      <form method="dialog" class="dialog__body">
        <h2 class="dialog__title">Save this outfit</h2>
        <div class="field">
          <label class="field__label" for="save-name">Name</label>
          <input class="input" id="save-name" name="name" maxlength="80" value="${esc(defaultName)}" required>
          <p class="field__hint">You'll find it on the Saved page.</p>
        </div>
        <div class="dialog__actions">
          <button class="btn" value="cancel" type="submit" formnovalidate>Cancel</button>
          <button class="btn btn--primary" value="ok" type="submit">Save outfit</button>
        </div>
      </form>`;
    document.body.append(dlg);
    const input = dlg.querySelector("input");
    dlg.addEventListener("close", () => {
      resolve(dlg.returnValue === "ok" ? input.value.trim() || defaultName : null);
      dlg.remove();
    });
    dlg.showModal();
    input.select();
  });
}

export function bindOutfitActions(root, outfit, { onUpdate, onAnother } = {}) {
  const article = root.querySelector(".outfit");
  if (!article) return;

  const wearBtn = article.querySelector("[data-wear]");
  wearBtn?.addEventListener("click", async () => {
    const on = wearBtn.getAttribute("aria-pressed") !== "true";
    wearBtn.disabled = true;
    try {
      const res = await api.recommendations.wear(outfit.id, on);
      outfit.worn_at = res.worn_at;
      wearBtn.setAttribute("aria-pressed", String(on));
      wearBtn.textContent = on ? "Wearing it today" : "I'm wearing this today";
      toast(on ? "Logged. These pieces will rest for a few days in new suggestions." : "Unlogged.", "success", { duration: 3000 });
    } catch (err) {
      toastError(err);
    } finally {
      wearBtn.disabled = false;
    }
  });

  const shareBtn = article.querySelector("[data-share]");
  if (shareBtn && navigator.share) {
    shareBtn.hidden = false;
    shareBtn.addEventListener("click", async () => {
      const photo = article.querySelector(".outfit-photo__img");
      const text = `My outfit for ${label(outfit.occasion).toLowerCase()}: ${outfit.items.map((i) => i.name).join(", ")}`;
      try {
        let files;
        if (photo) {
          const blob = await fetch(photo.src).then((r) => r.blob()).catch(() => null);
          if (blob) files = [new File([blob], "fitcheck-outfit.jpg", { type: blob.type || "image/jpeg" })];
        }
        if (files && navigator.canShare?.({ files })) await navigator.share({ files, text, title: "FitCheck.AI outfit" });
        else await navigator.share({ text, title: "FitCheck.AI outfit" });
      } catch (err) {
        if (err?.name !== "AbortError") toastError(err, "Couldn't share this outfit.");
      }
    });
  }

  article.querySelector("[data-download-look]")?.addEventListener("click", async () => {
    const slug = (outfit.saved_name || `${outfit.occasion}-outfit`).toLowerCase().replace(/[^a-z0-9]+/g, "-");
    try {
      const photo = article.querySelector(".outfit-photo__img");
      if (!photo) return toast("The photo isn't ready yet.", "info");
      const a = document.createElement("a");
      try {
        const blob = await (await fetch(photo.src)).blob();
        const ext = blob.type.includes("png") ? "png" : blob.type.includes("webp") ? "webp" : "jpg";
        a.href = URL.createObjectURL(blob);
        a.download = `fitcheck-${slug}.${ext}`;
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      } catch {
        // a photo served without CORS can't be read: open it so it can be saved
        a.href = photo.src;
        a.target = "_blank";
        a.rel = "noopener";
      }
      document.body.append(a);
      a.click();
      a.remove();
    } catch (err) {
      toastError(err, "Couldn't save the picture.");
    }
  });

  article.querySelectorAll("[data-feedback]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const wanted = btn.dataset.feedback;
      const verdict = outfit.feedback === wanted ? null : wanted; // second click clears it
      const buttons = article.querySelectorAll("[data-feedback]");
      buttons.forEach((b) => (b.disabled = true));
      try {
        await api.recommendations.feedback(outfit.id, verdict);
        outfit.feedback = verdict;
        buttons.forEach((b) => {
          const on = b.dataset.feedback === verdict;
          b.setAttribute("aria-pressed", String(on));
          if (b.dataset.feedback === "like") b.lastChild.textContent = on ? " Liked" : " Like";
        });
        toast(verdict === "like" ? "Noted. More like this."
          : verdict === "dislike" ? "Noted. Fewer like this." : "Rating cleared.", "success", { duration: 2500 });
        onUpdate?.(outfit);
      } catch (err) {
        toastError(err);
      } finally {
        buttons.forEach((b) => (b.disabled = false));
      }
    });
  });

  const saveBtn = article.querySelector("[data-save]");
  saveBtn?.addEventListener("click", async () => {
    const name = await askName(outfit.saved_name || `${label(outfit.occasion)} outfit`);
    if (name === null) return;
    saveBtn.disabled = true;
    try {
      const res = await api.recommendations.save(outfit.id, name);
      outfit.saved = true;
      outfit.saved_id = res.saved_id;
      outfit.saved_name = res.name;
      saveBtn.textContent = "Saved";
      saveBtn.classList.remove("btn--primary");
      saveBtn.setAttribute("aria-pressed", "true");
      toast(`Saved as "${res.name}".`, "success");
      onUpdate?.(outfit);
    } catch (err) {
      toastError(err);
    } finally {
      saveBtn.disabled = false;
    }
  });

  article.querySelector("[data-another]")?.addEventListener("click", (e) => onAnother?.(e.currentTarget));
}
