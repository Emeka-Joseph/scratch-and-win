(function () {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  // Mobile sidebar
  const sidebar = $(".sidebar");
  $$(".menu-btn").forEach(b => b.addEventListener("click", () => sidebar && sidebar.classList.toggle("open")));

  // Flash dismiss + auto-hide
  $$(".flash").forEach(f => {
    const close = () => { f.style.transition = "opacity .3s"; f.style.opacity = 0; setTimeout(() => f.remove(), 300); };
    f.querySelector("button")?.addEventListener("click", close);
    if (!f.classList.contains("error")) setTimeout(close, 6000);
  });

  // Dropdowns
  document.addEventListener("click", e => {
    const toggle = e.target.closest("[data-dropdown]");
    $$(".dropdown.open").forEach(d => { if (!toggle || d !== toggle.parentElement) d.classList.remove("open"); });
    if (toggle) { e.preventDefault(); toggle.parentElement.classList.toggle("open"); }
  });

  // Copy-to-clipboard
  $$("[data-copy]").forEach(btn => btn.addEventListener("click", async () => {
    const text = btn.getAttribute("data-copy");
    try { await navigator.clipboard.writeText(text); } catch (e) {
      const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
      document.execCommand("copy"); ta.remove();
    }
    const old = btn.innerHTML; btn.innerHTML = '<i class="bi bi-check2"></i> Copied';
    setTimeout(() => (btn.innerHTML = old), 1600);
  }));

  // Confirm on destructive forms
  $$("form[data-confirm]").forEach(f => f.addEventListener("submit", e => {
    if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault();
  }));

  // Color pickers <-> hex text inputs, and live preview vars
  const preview = $(".phone-screen");
  function luminance(hex) {
    const c = hex.replace("#", "").match(/../g).map(x => parseInt(x, 16) / 255)
      .map(v => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  const onColor = hex => { const l = luminance(hex); return (l + 0.05) / 0.05 > 1.05 / (l + 0.05) ? "#111111" : "#FFFFFF"; };
  function applyPreview() {
    if (!preview) return;
    $$(".color-field").forEach(cf => {
      const key = cf.getAttribute("data-var"); const val = cf.querySelector("input[type=color]").value;
      preview.style.setProperty(`--pv-${key}`, val);
      preview.style.setProperty(`--pv-on-${key}`, onColor(val));
    });
  }
  $$(".color-field").forEach(cf => {
    const picker = cf.querySelector("input[type=color]"); const text = cf.querySelector("input[type=text]");
    picker.addEventListener("input", () => { text.value = picker.value.toUpperCase(); applyPreview(); });
    text.addEventListener("input", () => {
      let v = text.value.trim(); if (!v.startsWith("#")) v = "#" + v;
      if (/^#[0-9a-fA-F]{6}$/.test(v)) { picker.value = v; applyPreview(); }
    });
  });
  applyPreview();

  // Live preview text bindings
  $$("[data-preview]").forEach(inp => {
    const target = $(inp.getAttribute("data-preview"));
    const fallback = target ? target.textContent : "";
    const sync = () => { if (target) target.textContent = inp.value || fallback; };
    inp.addEventListener("input", sync); sync();
  });

  // Logo upload preview
  $$(".dropzone input[type=file]").forEach(inp => inp.addEventListener("change", () => {
    const file = inp.files[0]; if (!file) return;
    const url = URL.createObjectURL(file);
    $$(".logo-preview-target").forEach(el => (el.innerHTML = `<img src="${url}" alt="">`));
    const name = inp.closest(".dropzone").querySelector(".file-name"); if (name) name.textContent = file.name;
  }));

  // Auto slug from brand name
  const nameInput = $("#brand-name"), slugInput = $("#brand-slug");
  if (nameInput && slugInput && !slugInput.value) {
    let touched = false;
    slugInput.addEventListener("input", () => (touched = true));
    nameInput.addEventListener("input", () => {
      if (!touched) slugInput.value = nameInput.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      $$(".slug-echo").forEach(el => (el.textContent = slugInput.value || "your-brand"));
    });
    slugInput.addEventListener("input", () => $$(".slug-echo").forEach(el => (el.textContent = slugInput.value || "your-brand")));
  }

  // Repeating prize rows
  const addPrize = $("#add-prize-row");
  if (addPrize) {
    addPrize.addEventListener("click", () => {
      const tpl = $("#prize-row-template"); const list = $("#prize-rows");
      list.appendChild(tpl.content.cloneNode(true));
    });
    document.addEventListener("click", e => {
      const rm = e.target.closest(".remove-row"); if (rm) rm.closest(".prize-row").remove();
    });
  }
})();
