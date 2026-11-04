// FitCheck.AI — frontend configuration
// Swayam Shakya
//
// The pages are served by the FitCheck.AI server and call its API on the
// same origin, so there is no server address to configure here.

export const config = Object.freeze({
  appName: "FitCheck.AI",
  author: "Swayam Shakya",
  storageKeys: {
    theme: "fitcheck.theme",
    token: "fitcheck.token",
  },
});
