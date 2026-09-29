// Parses every Mermaid block handed to it, in ONE Node process, and
// says which ones Mermaid itself rejects (REQ-DOCS-122 criterion 12).
//
// Called only by `mothman docs validate`, never directly. Input on
// stdin is a JSON array of {id, source}; output on stdout is a JSON
// array of {id, ok, diagramType, error}. One process for the whole
// batch because Node plus jsdom plus Mermaid costs about a second to
// start, and a validator that paid that per block would not fit in
// `mothman check`.
//
// The pinned version is the one GitHub renders (11.17.2, checked
// 2026-09-28), because in explainers slice 1 GitHub is the only
// renderer a reader sees. Slice 2 adds a second parse against the
// vendored 12.x the dashboard will use.
//
// jsdom is there because Mermaid reaches for a DOM (DOMPurify) even to
// parse. Proven headless before this was written: flowchart and state
// blocks parsed, a broken block returned its line, 1.2s for the lot.
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
for (const k of ['DOMParser', 'Element', 'HTMLElement', 'SVGElement', 'Node']) {
  globalThis[k] = dom.window[k];
}

const { default: mermaid } = await import('mermaid');
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });

let input = '';
for await (const chunk of process.stdin) input += chunk;
const blocks = JSON.parse(input);

const results = [];
for (const { id, source } of blocks) {
  try {
    const r = await mermaid.parse(source);
    results.push({ id, ok: true, diagramType: r.diagramType ?? null, error: null });
  } catch (e) {
    results.push({ id, ok: false, diagramType: null, error: String(e?.message ?? e) });
  }
}
process.stdout.write(JSON.stringify(results));
