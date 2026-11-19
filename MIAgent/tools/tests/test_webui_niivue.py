"""Regression checks for the MIAgent NiiVue bridge."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


WEBUI = Path(__file__).resolve().parents[1] / "webui"
sys.path.insert(0, str(WEBUI))

import app  # noqa: E402


class NiiVueBridgeTest(unittest.TestCase):
    def test_label_colormap_is_applied_to_overlay_volume(self) -> None:
        handler = app.NIIVUE_REVIEW_HANDLERS
        self.assertIn("s.setColormapLabel(B.colormap);", handler)
        self.assertNotIn("C.setColormapLabel(s.id, B.colormap);", handler)

    def test_readable_toolbar_override_is_present(self) -> None:
        page = app.render_niivue_page()
        self.assertIn("color-scheme: light", page)
        self.assertIn("body > #app button", page)

    def test_viewer_controls_are_loaded(self) -> None:
        page = app.render_niivue_page()
        self.assertIn('src="static/niivue-controls.js?v=compact-slices-3"', page)
        self.assertIn('src="niivue/niivue/index.js?v=compact-slices-3"', page)
        self.assertIn('aria-label="Show 3D volume" aria-pressed="false"', page)
        self.assertIn('#miagent-review { display: none !important; }', page)

    def test_bundle_customizations_are_applied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'index.js'
            path.write_text('/* @__PURE__ */ T(Ir, { ...g }),\nhideUI: EA(3),\ng.isLoaded = !0, g.body = null,')
            source = app.patched_niivue_script(path)
        self.assertNotIn('T(Ir,', source)
        self.assertIn('hideUI: EA(0)', source)
        self.assertIn('window.miagentNiivue.configure(g)', source)

    def test_contrast_presets_are_visible_and_offset_aware(self) -> None:
        page = app.render_niivue_page()
        toolbar = page.split('<div id="miagent-contrast-toolbar"', 1)[1].split('</div>', 1)[0]
        for preset in ("lung", "abdomen", "soft", "bone", "auto"):
            self.assertIn(f'value="{preset}"', toolbar)
        self.assertIn('range[0] + huOffset', page)
        self.assertIn('range[1] + huOffset', page)
        self.assertNotIn('hidden', toolbar)


if __name__ == "__main__":
    unittest.main()
