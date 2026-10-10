(() => {
  const $ = (id) => document.getElementById(id);
  const screens = ["home", "loading", "result"];
  let current = null; // { image: dataURL (normalised jpeg), steps: [...] }

  const SAMPLES = [
    { id: "s1", label: "Sign slip" },
    { id: "s2", label: "Lost a solution" },
    { id: "s3", label: "All correct" },
    { id: "s4", label: "Notebook page" },
  ];
  // honest progress: the server does not stream its stages, so show what happens, not which step is running
  const WAIT_TEXT = "Finding lines → reading them (vision model) → checking each step (SymPy) → reading the suspect line again → marking. Usually 5–25 s";
  let stageTimer = null;
  function startStages() {
    const t0 = Date.now();
    const tick = () => {
      const s = (Date.now() - t0) / 1000;
      $("stage").textContent = `${WAIT_TEXT} · ${Math.floor(s)} s`;
    };
    tick(); stageTimer = setInterval(tick, 500);
  }
  function stopStages() { clearInterval(stageTimer); stageTimer = null; }

  function show(name) {
    if (name !== "loading") stopStages();
    screens.forEach((s) => ($(s).hidden = s !== name));
    $("error").hidden = true;
    $("ctaText").textContent = name === "result" ? "Check another photo" : "Check my work — take a photo";
    window.scrollTo({ top: 0 });
  }

  function fail(msg) {
    show(current ? "result" : "home");
    $("error").textContent = msg;
    $("error").hidden = false;
  }

  const HINT_LABEL = {
    sign: "Sign", arithmetic: "Arithmetic", distribution: "Distribution", dropped_term: "Missing term",
    lost_solution: "Lost a solution", extra_solution: "Extra solution", check_step: "Check this step",
  };
  const REL_LABEL = { start: "start", equivalent: "holds", not_equivalent: "breaks", unreadable: "can't read", unsupported: "not checked", prose: "words", doubtful: "read 2 ways" };

  function render(out, image, read) {
    // read = what RedPen originally read from the photo (kept across re-checks)
    current = { image, steps: out.steps, read: read || out.steps.map((s) => s.text) };
    const v = out.verdict;
    const card = $("verdictCard");
    card.classList.remove("slip", "ok", "unsure");
    $("readDetails").open = false;
    const unsure = v.uncertain_lines || [];
    if (!v.first_slip_line && unsure.length) {
      card.classList.add("unsure");
      $("bigNum").textContent = `Line ${unsure[0]}?`;
      $("bigSub").textContent = "I read this line two different ways";
      $("hintChip").hidden = true;
      $("explain").textContent = "RedPen only circles a line when two readings agree. Check that line below, fix it if I misread it, and re-check.";
      $("readDetails").open = true;
    } else if (v.first_slip_line) {
      card.classList.add("slip");
      $("bigNum").textContent = `Line ${v.first_slip_line}`;
      $("bigSub").textContent = "is where your work first breaks";
      $("hintChip").textContent = HINT_LABEL[v.hint] || "Check this step";
      $("hintChip").hidden = false;
      $("explain").textContent = (v.explanation || "") + " Fix that line and everything after it.";
    } else {
      card.classList.add("ok");
      const done = v.steps_checked ?? v.checked, total = v.steps_total ?? v.maths_lines;
      $("hintChip").hidden = true;
      if (!total) {
        $("bigNum").textContent = "Nothing to check";
        $("bigSub").textContent = "RedPen needs at least two lines of working";
        $("explain").textContent = "It checks each line against the one before it. Open “What RedPen read” to see what it found.";
      } else {
        $("bigNum").textContent = `${done}/${total}`;
        $("bigSub").textContent = done === total ? "steps hold — nice work" : "steps checked (some couldn't be read)";
        $("explain").textContent = done === total ? "Every line follows from the one before." : "Open “What RedPen read” and fix the lines marked “can't read”.";
      }
    }
    const edited = out.steps.map((s, i) => (s.text !== current.read[i] ? i + 1 : 0)).filter(Boolean);
    if (edited.length) {
      $("explain").textContent += ` Line${edited.length > 1 ? "s" : ""} ${edited.join(", ")} checked as you typed ${edited.length > 1 ? "them" : "it"} (shown as “typed …” in the margin).`;
    }
    $("marked").src = out.image;
    $("download").href = out.image;
    const ol = $("lines");
    ol.innerHTML = "";
    out.steps.forEach((s, i) => {
      const li = document.createElement("li");
      const n = document.createElement("span"); n.className = "n"; n.textContent = i + 1;
      const inp = document.createElement("input"); inp.value = s.text; inp.dataset.i = i; inp.setAttribute("aria-label", `Line ${i + 1}`);
      inp.autocapitalize = "off"; inp.spellcheck = false;
      const rel = s.doubtful ? "doubtful" : s.relation;
      const tag = document.createElement("span"); tag.className = `tag ${rel}`; tag.textContent = REL_LABEL[rel] || rel;
      li.append(n, inp, tag); ol.append(li);
    });
    const t = out.timings_ms || {};
    $("howDecided").innerHTML = `
      <p><b>Line finding:</b> ${out.mode === "model-located" ? "the photo didn't look like neat lines, so the vision model located them" : "classical computer vision (projection profile + deskew)"}.</p>
      <p><b>Reading:</b> ${out.model || "—"}. The model only copies what is written; it is told never to fix mistakes.</p>
      <p><b>Before circling:</b> ${out.rechecked ? "the suspect line and the one before it were read a second time, zoomed in. " + (unsure.length ? "The readings disagreed, so RedPen asks instead of accusing." : "The readings agreed.") : "nothing to circle, no second reading needed."}</p>
      ${out.verdict.culprit ? `<p><b>Pointing:</b> SymPy found that the written “${out.verdict.culprit.replace(/[<>&]/g, "")}” is the part that breaks the step; ${out.verdict.term_circled ? "the vision model located it on your photo, so only that part is circled." : "the vision model could not place it, so the whole line is circled."}</p>` : ""}
      <p><b>Verifying:</b> SymPy compares each line with the previous readable one — solution sets for equations, symbolic + numeric identity for expressions. Lines it can't read are skipped, never called wrong.</p>
      <p><b>Time:</b> ${Object.entries(t).map(([k, ms]) => `${k} ${ms} ms`).join(" · ") || "—"}</p>`;
    show("result");
  }

  async function post(path, body) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 59000);
    let r;
    try {
      r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctl.signal });
    } catch (e) {
      throw new Error(e.name === "AbortError" ? "That took too long. Try again, or open a sample." : "Network problem. Try again.");
    } finally { clearTimeout(timer); }
    let data = {};
    try { data = await r.json(); } catch (_) { /* ignore */ }
    if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
    return data;
  }

  async function normalise(file) {
    // EXIF-aware decode, longest side 1600 px, JPEG ~0.85 (keeps uploads well under platform limits)
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" }).catch(() => null);
    const src = bmp || await new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = URL.createObjectURL(file); });
    const w = src.width, h = src.height, k = Math.min(1, 1600 / Math.max(w, h));
    const c = document.createElement("canvas"); c.width = Math.round(w * k); c.height = Math.round(h * k);
    c.getContext("2d").drawImage(src, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.85);
  }

  $("file").addEventListener("change", async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = "";
    if (!f) return;
    show("loading"); startStages();
    try {
      const image = await normalise(f);
      const out = await post("/api/grade", { image });
      render(out, image);
    } catch (err) { fail(err.message || "Could not check this photo."); }
  });

  $("recheck").addEventListener("click", async () => {
    if (!current) return;
    const steps = current.steps.map((s, i) => {
      const text = document.querySelector(`#lines input[data-i="${i}"]`).value;
      return { text, box: s.box, kind: s.kind, edited: text !== current.read[i] };
    });
    $("recheck").disabled = true; $("recheck").textContent = "Re-checking…";
    try {
      const out = await post("/api/regrade", { image: current.image, steps });
      render(out, current.image, current.read);
      $("readDetails").open = true;
    } catch (err) { fail(err.message); }
    finally { $("recheck").disabled = false; $("recheck").textContent = "Re-check — no AI call"; }
  });

  async function openSample(id) {
    show("loading");
    try {
      const [res, img] = await Promise.all([fetch(`samples/${id}.result.json`).then((r) => r.json()), fetch(`samples/${id}.jpg`).then((r) => r.blob())]);
      const image = await new Promise((ok) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.readAsDataURL(img); });
      render(res, image);
    } catch (err) { fail("Could not load the sample."); }
  }

  const wrap = $("samples");
  SAMPLES.forEach((s) => {
    const b = document.createElement("button");
    b.className = "sample"; b.type = "button";
    b.innerHTML = `<img src="samples/${s.id}.jpg" alt="" loading="lazy"><span>${s.label}</span>`;
    b.addEventListener("click", () => openSample(s.id));
    wrap.append(b);
  });
})();
