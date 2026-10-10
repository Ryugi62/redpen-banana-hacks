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
  const STAGES = [
    [0, "Finding your lines…"], [2, "Reading each line (vision model)…"], [7, "Checking every step with SymPy…"],
    [10, "Reading the suspect line again, zoomed in, before circling it…"], [20, "Still working — free models can be slow…"],
  ];
  let stageTimer = null;
  function startStages() {
    const t0 = Date.now();
    const tick = () => {
      const s = (Date.now() - t0) / 1000;
      const label = STAGES.filter(([at]) => s >= at).pop()[1];
      $("stage").textContent = `${label} ${Math.floor(s)} s`;
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

  function render(out, image) {
    current = { image, steps: out.steps };
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
      $("bigNum").textContent = `${v.checked}/${v.maths_lines}`;
      $("bigSub").textContent = v.checked === v.maths_lines ? "steps hold — nice work" : "lines verified (some couldn't be read)";
      $("hintChip").hidden = true;
      $("explain").textContent = v.checked === v.maths_lines ? "Every line follows from the one before." : "Open “What RedPen read” and fix the lines marked “can't read”.";
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
    const steps = current.steps.map((s, i) => ({ text: document.querySelector(`#lines input[data-i="${i}"]`).value, box: s.box, kind: s.kind }));
    $("recheck").disabled = true; $("recheck").textContent = "Re-checking…";
    try {
      const out = await post("/api/regrade", { image: current.image, steps });
      render(out, current.image);
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
