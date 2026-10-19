// "Prueba": the same performance ("Un día de ventas de Morfi") acted by different AI models, side by side.
// models/tests/index.json lists the entries ([{id, label}]); when the section is opened each
// models/tests/<id>.json is read (title, audio, camera, face curves, the model, what it cost) and its
// card gets a play button. The GLB of an entry only loads when it is played (ScenePlayer.playTest).
// An entry whose JSON is not there yet says "En preparación". Costs are USD; null shows as "—".
import type { ScenePlayer, TestEntry } from './scenes';

interface IndexItem { id: string; label: string }

const SAFE_ID = /^[a-z0-9_-]{1,32}$/i;
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const usd = (v: number | null | undefined) =>
  typeof v === 'number' && Number.isFinite(v) ? '$' + v.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';

/** "Creación $x · Revisión $y · Publicación $z · Total $t" */
export function costLine(e: Pick<TestEntry, 'costs'>): string {
  const c = e.costs ?? {};
  return `Creación ${usd(c.creation)} · Revisión ${usd(c.review)} · Publicación ${usd(c.publish)} · Total ${usd(c.total)}`;
}

/** "Cambios en la revisión: N" */
export function changesLine(e: Pick<TestEntry, 'changes'>): string {
  return `Cambios en la revisión: ${typeof e.changes === 'number' && Number.isFinite(e.changes) ? e.changes : '—'}`;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = '', text = ''): HTMLElementTagNameMap[K] {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text) n.textContent = text;
  return n;
}

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const r = await fetch(url);
    if (!r.ok || !(r.headers.get('content-type') ?? '').includes('json')) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

const validEntry = (e: unknown): e is TestEntry => {
  const t = e as TestEntry | null;
  return !!t && typeof t.action === 'string' && typeof t.title === 'string' && typeof t.audio === 'string' &&
    t.frames > 0 && !!t.props && typeof t.props === 'object';
};

export interface TestsSection {
  /** the entries that were found (after the section was opened) */
  readonly list: { id: string; label: string; action: string; title: string; model: string; dur: number }[];
  /** play an entry by id (loads the section and the entry's GLB first); false if there is no such entry */
  play: (id: string) => Promise<boolean>;
}

/**
 * Wire the "Prueba" <details>: nothing is fetched until it is opened. `base` is the models/tests/ folder
 * (the one that has index.json), `box` the <details>, `list` the container the cards go in.
 */
export function setupTests(sp: ScenePlayer, base: string, box: HTMLDetailsElement, list: HTMLElement, hint: HTMLElement): TestsSection {
  const found = new Map<string, { label: string; entry: TestEntry }>();
  let loading: Promise<void> | null = null;

  function card(item: IndexItem, entry: TestEntry | null): HTMLElement {
    const root = el('div', entry ? 'test' : 'test pending');
    root.dataset.test = item.id;
    if (!entry) {
      root.append(el('strong', 'stitle', item.label), el('span', 'tstate', 'En preparación'));
      return root;
    }
    const b = el('button', 'scene video');
    b.type = 'button';
    b.dataset.scene = entry.action;
    const icon = el('span', 'play');
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML = '<svg viewBox="0 0 24 24"><path d="M7 4.8v14.4L19 12z" /></svg>';
    const sub = el('span', 'sdur', `${entry.title} · ${mmss(entry.frames / (entry.fps || 30))}`);
    b.append(icon, el('span', 'stitle', item.label), sub);
    b.addEventListener('click', () => {
      if (sp.state?.key === entry.action) { sp.togglePause(); return; }
      sub.textContent = 'Cargando…';
      void sp.playTest(entry.action).then((ok) => {
        sub.textContent = ok ? `${entry.title} · ${mmss(entry.frames / (entry.fps || 30))}` : 'No se pudo cargar, intenta otra vez';
      });
    });
    root.append(b);
    if (entry.model) root.append(el('p', 'tmodel', entry.model));
    root.append(el('p', 'tcost', costLine(entry)), el('p', 'tcost', changesLine(entry)));
    if (typeof entry.note === 'string' && entry.note.trim()) root.append(el('p', 'tcost tnote', entry.note.trim()));
    return root;
  }

  async function load(): Promise<void> {
    hint.textContent = 'Cargando la prueba…';
    const index = await fetchJson<IndexItem[]>(base + 'index.json');
    const items = Array.isArray(index) ? index.filter((i) => i && SAFE_ID.test(i.id) && typeof i.label === 'string') : [];
    if (!items.length) {
      hint.textContent = 'La prueba llega pronto.';
      return;
    }
    const entries = await Promise.all(items.map((i) => fetchJson<TestEntry>(`${base}${i.id}.json`)));
    list.replaceChildren();
    items.forEach((item, k) => {
      const entry = validEntry(entries[k]) ? entries[k] : null;
      if (entry) {
        found.set(item.id, { label: item.label, entry });
        sp.addTest(entry, `${base}${item.id}.glb`);
      }
      list.append(card(item, entry));
    });
    hint.textContent = 'La misma actuación, hecha por cada modelo. Costos en dólares (USD).';
  }

  const open = () => { loading ??= load(); void loading; };
  box.addEventListener('toggle', () => { if (box.open) open(); });
  if (box.open) open();

  const section: TestsSection = {
    get list() {
      return [...found].map(([id, v]) => ({ id, label: v.label, action: v.entry.action, title: v.entry.title, model: v.entry.model ?? '',
        dur: v.entry.frames / (v.entry.fps || 30) }));
    },
    play: async (id: string) => {
      open();
      await loading;
      const f = found.get(id);
      return f ? sp.playTest(f.entry.action) : false;
    },
  };
  return section;
}
