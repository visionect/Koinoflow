# Koinoflow frontend

React 19 + Vite + TypeScript (strict). Run `make up` from the repo root; see the main `CLAUDE.md` for day-to-day commands.

## Design system

The frontend uses shadcn/ui (Radix + Tailwind) with theme tokens declared in [src/index.css](src/index.css). Always prefer semantic tokens over raw Tailwind palettes so we keep light/dark parity and a single source of brand truth.

### Color tokens

| Token                                          | When to use                                                            |
| ---------------------------------------------- | ---------------------------------------------------------------------- |
| `background` / `foreground`                    | Page surface + primary text.                                           |
| `card` / `card-foreground`                     | Elevated panels.                                                       |
| `primary` / `accent`                           | Brand navy / amber. Use for primary actions and focus affordances.     |
| `muted` / `muted-foreground`                   | Low-emphasis surfaces and captions.                                    |
| `success` / `warning` / `info` / `destructive` | Status affordances. Always pair with the matching `-foreground` token. |
| `diff-add` / `diff-remove`                     | Additions / removals in diffs and version history.                     |
| `chart-1..5`                                   | Data viz hues. Perceptually spaced for color-vision safety.            |

Avoid raw `bg-emerald-*`, `text-red-*`, `bg-blue-50`, etc. If you need a new semantic role, declare it in both `:root` and `.dark` in `index.css`, not inline.

### Typography scale

Five roles — no ad-hoc sizes. Everything on the page should map to one of these:

| Role    | Tailwind classes                        | Example                       |
| ------- | --------------------------------------- | ----------------------------- |
| display | `text-4xl font-semibold tracking-tight` | Marketing / split screens     |
| h1      | `text-3xl font-semibold tracking-tight` | Page title (use `PageHeader`) |
| h2      | `text-lg font-semibold`                 | Section titles, card titles   |
| body    | `text-sm`                               | Body text, form labels        |
| caption | `text-xs text-muted-foreground`         | Helper text, metadata, badges |

Use `PageHeader` for every top-level route; don't hand-roll h1s. Card titles are h2 via `CardTitle` (shadcn) — don't promote them to h1.

### Icons

- Single library: `lucide-react`. No Heroicons / Material / Font Awesome.
- Import names use the `Icon` suffix (`ChevronDownIcon`, `FileTextIcon`). Alias if needed: `import { FileCode as FileCodeIcon } from "lucide-react"`.
- Sizes: `size-4` (16px, inline with text) or `size-5` (20px, toolbar / header). Avoid `h-3 w-3` ad-hoc sizes.
- Decorative icons next to a text label get `aria-hidden`. Icons carrying meaning on their own need `aria-label`.

### Fonts

- Body: `--font-sans` (Geist Variable with a full system fallback stack).
- Code, `kbd`, `pre`, `samp`: `--font-mono` (Geist Mono Variable). Applied automatically in `index.css`.

### Radius

`--radius: 0.75rem`. Derived sizes (`--radius-sm/md/lg/xl/2xl/3xl/4xl`) scale from it. Tune centrally; don't hardcode `rounded-[12px]`.

## Type / lint / test

```bash
npm run typecheck
npm run lint
npm run test
```
