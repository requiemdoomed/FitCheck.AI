// Shown by the service worker when a page isn't cached and there's no connection.
// Swayam Shakya
import { initTheme } from "../theme.js";

initTheme();
document.querySelector("[data-retry]").addEventListener("click", () => location.reload());
window.addEventListener("online", () => location.reload());
