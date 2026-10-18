// The "Estilo" panel: its own button in the toolbar and its own panel (left side on a
// desktop, bottom sheet on a phone), apart from "Controles". Switches and sliders for the
// contour and the motion effects; the settings are kept in this browser.
import type { StyleSettings } from './style';

interface SliderSpec {
  key: keyof StyleSettings;
  label: string;
  min: number;
  max: number;
  step: number;
  show: (v: number) => string;
}

const pct = (v: number) => `${Math.round(v * 100)}%`;

const OUTLINE_SLIDERS: SliderSpec[] = [
  { key: 'width', label: 'Grosor', min: 0.5, max: 4, step: 0.1, show: (v) => `${v.toFixed(1)} px` },
  { key: 'glasses', label: 'Grosor en lentes', min: 1, max: 3, step: 0.1, show: (v) => `${v.toFixed(1)}×` },
  { key: 'ink', label: 'Intensidad', min: 0, max: 1, step: 0.05, show: pct },
  { key: 'thin', label: 'Se adelgaza a lo lejos', min: 0, max: 1, step: 0.05, show: pct },
];
const FX_SLIDERS: SliderSpec[] = [
  { key: 'smear', label: 'Barrido al moverse rápido', min: 0, max: 1, step: 0.05, show: pct },
  { key: 'squash', label: 'Estirar y aplastar', min: 0, max: 1, step: 0.05, show: pct },
  { key: 'sensitivity', label: 'Sensibilidad', min: 0, max: 1, step: 0.05, show: pct },
];

export interface StylePanel {
  /** show the values of these settings */
  sync(s: StyleSettings): void;
  open(on: boolean): void;
}

/** the filled part of a slider's track (style.css) */
function fill(r: HTMLInputElement, spec: SliderSpec): void {
  r.style.setProperty('--p', `${((Number(r.value) - spec.min) / (spec.max - spec.min)) * 100}%`);
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}

export function createStylePanel(
  app: HTMLElement, toolbar: HTMLElement,
  onChange: (key: keyof StyleSettings, value: number | boolean) => void, onReset: () => void,
): StylePanel {
  const toggle = el('button', 'style-toggle', 'Estilo');
  toggle.type = 'button';
  toggle.id = 'style-toggle';
  toggle.setAttribute('aria-controls', 'style-panel');
  toggle.setAttribute('aria-expanded', 'false');
  toolbar.append(toggle);

  const panel = el('aside', 'style-panel');
  panel.id = 'style-panel';
  panel.setAttribute('aria-label', 'Estilo de Morfi');
  const head = el('header', 'sp-head');
  const title = el('div');
  title.append(el('h2', 'sp-title', 'Estilo'), el('p', 'sp-sub', 'Cómo se dibuja Morfi'));
  const close = el('button', 'sp-close');
  close.type = 'button';
  close.setAttribute('aria-label', 'Cerrar estilo');
  close.title = 'Cerrar';
  close.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>';
  head.append(title, close);
  panel.append(head);

  const inputs = new Map<keyof StyleSettings, { input: HTMLInputElement; out?: HTMLOutputElement; spec?: SliderSpec }>();

  function section(name: string, sw: keyof StyleSettings, hint: string, sliders: SliderSpec[]): void {
    const sec = el('section', 'sp-sec');
    const row = el('label', 'sp-switch');
    const cb = el('input');
    cb.type = 'checkbox';
    cb.setAttribute('role', 'switch');
    cb.addEventListener('change', () => onChange(sw, cb.checked));
    const txt = el('span', 'sp-switch-text');
    txt.append(el('strong', '', name), el('small', '', hint));
    row.append(txt, cb, el('span', 'sp-track'));
    sec.append(row);
    inputs.set(sw, { input: cb });
    const box = el('div', 'sp-sliders');
    for (const spec of sliders) {
      const id = 'sp-' + spec.key;
      const lab = el('label', 'sp-slider');
      lab.htmlFor = id;
      const top = el('span', 'sp-row');
      const out = el('output');
      out.htmlFor.add(id);
      top.append(el('span', '', spec.label), out);
      const r = el('input');
      r.type = 'range';
      r.id = id;
      r.min = String(spec.min);
      r.max = String(spec.max);
      r.step = String(spec.step);
      r.addEventListener('input', () => {
        fill(r, spec);
        out.value = spec.show(Number(r.value));
        onChange(spec.key, Number(r.value));
      });
      lab.append(top, r);
      box.append(lab);
      inputs.set(spec.key, { input: r, out, spec });
    }
    sec.append(box);
    panel.append(sec);
  }
  section('Contorno', 'outline', 'Una línea fina en las orillas', OUTLINE_SLIDERS);
  section('Efectos de movimiento', 'fx', 'Barrido y rebote al moverse', FX_SLIDERS);

  const reset = el('button', 'sp-reset', 'Restablecer');
  reset.type = 'button';
  reset.addEventListener('click', onReset);
  panel.append(reset);
  app.append(panel);

  let isOpen = false;
  function open(on: boolean): void {
    if (on === isOpen) return;
    isOpen = on;
    panel.classList.toggle('open', on);
    toggle.classList.toggle('on', on);
    toggle.setAttribute('aria-expanded', String(on));
    // one panel at a time on phones; on wide screens both fit side by side ("Controles" does the same)
    if (on) document.dispatchEvent(new CustomEvent('morfi:panel-open', { detail: 'style' }));
  }
  toggle.addEventListener('click', () => open(!isOpen));
  close.addEventListener('click', () => { open(false); toggle.focus(); });
  document.addEventListener('morfi:panel-open', (e) => {
    if ((e as CustomEvent).detail !== 'style' && window.matchMedia('(max-width: 720px)').matches) open(false);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen) { open(false); toggle.focus(); }
  });

  return {
    open,
    sync(s: StyleSettings): void {
      for (const [key, { input, out, spec }] of inputs) {
        const v = s[key];
        if (typeof v === 'boolean') input.checked = v;
        else if (spec) {
          input.value = String(v);
          fill(input, spec);
          if (out) out.value = spec.show(v);
        }
      }
      panel.querySelectorAll<HTMLElement>('.sp-sec').forEach((sec, i) => {
        sec.classList.toggle('off', !(i === 0 ? s.outline : s.fx));
      });
    },
  };
}
