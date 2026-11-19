(() => {
  const instances = [];
  let renderEnabled = false;
  const renderToggle = document.getElementById("miagent-render-toggle");
  function setLayout(nv) {
    const layout = [
      { sliceType: 0, position: [0, 0, 0.5, 0.5] },
      { sliceType: 2, position: [0.5, 0, 0.5, 0.5] },
      { sliceType: 1, position: [0, 0.5, 0.5, 0.5] },
    ];
    if (renderEnabled) layout.push({ sliceType: 4, position: [0.5, 0.5, 0.5, 0.5] });
    nv.setCustomLayout(layout);
  }
  renderToggle.addEventListener("click", () => {
    renderEnabled = !renderEnabled;
    renderToggle.setAttribute("aria-pressed", String(renderEnabled));
    renderToggle.title = renderEnabled ? "Hide 3D volume" : "Show 3D volume";
    renderToggle.setAttribute("aria-label", renderToggle.title);
    instances.forEach(setLayout);
  });
  function configure(nv) {
    if (nv.miagentConfigured) return;
    nv.miagentConfigured = true;
    instances.push(nv);
    nv.opts.crosshairWidth = 0.7;
    nv.opts.crosshairWidthUnit = "mm";
    nv.opts.crosshairGap = 1;
    nv.opts.multiplanarShowRender = 0;
    setLayout(nv);

    // Limit only crosshair geometry, leaving image bounds and navigation intact.
    const drawCrosshair = nv.drawCrosshairs3D.bind(nv);
    nv.drawCrosshairs3D = (...args) => {
      const extents = nv.sceneExtentsMinMax;
      nv.sceneExtentsMinMax = (useMM) => {
        const center = nv.frac2mm(nv.scene.crosshairPos, 0, useMM);
        return [Array.from(center, (v) => v - 4),
                Array.from(center, (v) => v + 4), [8, 8, 8]];
      };
      try {
        return drawCrosshair(...args);
      } finally {
        nv.sceneExtentsMinMax = extents;
      }
    };
    let drag = null;
    nv.canvas.addEventListener("mousedown", (event) => {
      if (event.button !== 2) return;
      const point = nv.getNoPaddingNoBorderCanvasRelativeMousePosition(event, nv.canvas);
      const tile = nv.tileIndex(point.x * nv.uiData.dpr, point.y * nv.uiData.dpr);
      if (tile < 0) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      drag = {
        contrast: event.ctrlKey, render: nv.screenSlices[tile].axCorSag === 4,
        y: event.clientY, pan: Array.from(nv.scene.pan2Dxyzmm),
        scale: nv.scene.volScaleMultiplier,
      };
      nv.uiData.windowX = event.clientX;
      nv.uiData.windowY = event.clientY;
    }, true);
    window.addEventListener("mousemove", (event) => {
      if (!drag) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (drag.contrast) {
        nv.windowingHandler(event.clientX, event.clientY);
        return;
      }
      const scale = Math.max(0.25, Math.min(12,
        (drag.render ? drag.scale : drag.pan[3]) * Math.exp((drag.y - event.clientY) / 160)));
      if (drag.render) nv.setScale(scale);
      else nv.setPan2Dxyzmm([...drag.pan.slice(0, 3), scale]);
    }, true);
    window.addEventListener("mouseup", (event) => {
      if (!drag || event.button !== 2) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      drag = null;
    }, true);
    window.addEventListener("blur", () => { drag = null; });
    nv.canvas.addEventListener("contextmenu", (event) => event.preventDefault());
    if (nv.crosshairs3D) nv.crosshairs3D.mm[0] = NaN;
    nv.drawScene();
  }
  window.miagentNiivue = { configure, instances };
})();
