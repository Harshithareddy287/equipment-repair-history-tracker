# Presentation

`index.html` is the slide deck. Its code snippets run the real `service_tracker`
package in the browser (Python compiled to WebAssembly, via Pyodide), and draw
charts and tables from the results.

## Present

Open `presentation/index.html` in Chrome or Edge. No server or install needed.

- **Next / back:** arrow keys, Page Up / Page Down, or the buttons at the bottom
- **Show the code:** code windows start collapsed. Drag the handle under a code window's bar down to open it to any height, or click the handle or **Show code** to open it to fit. Drag it back up to hide it again.
- **Run the snippet on this slide:** `R`, the Run button, or `Ctrl+Enter` (`Cmd+Enter`) in the code
- **Speaker notes and handoff lines:** `N`
- **15-minute rehearsal timer:** `T`. Hover it to see the time per speaker.
- `Esc` leaves the code editor so the arrow keys move slides again.

Python loads from `cdn.jsdelivr.net` the first time, which takes a few seconds,
and the bottom bar shows **Python ready** when it's done. Without internet, the
bar shows **Recorded runs**, and Run shows the output recorded when the bundle
was last built. Edited code only runs once Python has loaded.

## Edit

Each person owns their slides, marked by `data-owner`. A snippet is a
`<script type="text/x-python" id="s-...">` block inside its slide. Snippets
can `import deck` to draw `deck.stats`, `deck.table`, `deck.bars`,
`deck.columns`, `deck.compare`, `deck.stock`, `deck.timeline` and
`deck.terminal` output (see `deck.py`).

After changing a snippet, the package, the generator or `data/`, rebuild the
bundle (needs Python 3.11 or newer, the same as the package):

```bash
python presentation/build_bundle.py
```

This copies the code and data into `bundle.js` and re-records every snippet's
output, so the offline fallback matches. It fails if any snippet raises an
error. Commit `bundle.js` along with your change.
