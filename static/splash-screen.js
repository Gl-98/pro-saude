(function () {
  const splashScreen = document.getElementById("splashScreen");

  if (!splashScreen) {
    return;
  }

  const root = document.body;
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const displayDuration = prefersReducedMotion ? 1500 : 3000;
  const fadeDuration = prefersReducedMotion ? 150 : 700;

  function hideSplashScreen() {
    splashScreen.classList.add("is-hiding");
    window.setTimeout(() => {
      splashScreen.remove();
      root.classList.remove("splash-lock");
    }, fadeDuration);
  }

  function startSplashSequence() {
    root.classList.add("splash-lock");
    window.setTimeout(hideSplashScreen, displayDuration);
  }

  if (document.readyState === "complete") {
    startSplashSequence();
    return;
  }

  window.addEventListener("load", startSplashSequence, { once: true });
})();