# Building kikoeru-quasar on modern Node

The [kikoeru-quasar](https://github.com/kikoeru-project/kikoeru-quasar)
project is from 2020 and uses Quasar 1.x with `@quasar/app@1.9.6` and
`node-sass@4.14.1`. It does **not** build on a fresh Node 22 install.
This file is the sequence of patches that makes it build on
`arm64 macOS, Node 22.22.3, npm 10.9.8`. It took ~13 build attempts
to get through.

## When to use this

You're using `asmr-view`'s kikoeru-compat mode and want the **actual**
kikoeru-quasar SPA (with its polished `WorkTree` component, vue-plyr
audio, and admin pages) instead of the hand-rolled fallback at
`<ASMR_STACK_ROOT>/view/index.html`.

Skip this if the hand-rolled SPA meets your needs — it's already
shipped and works.

## The patch chain (run in order)

Assume `$SRC` is a fresh `git clone https://github.com/kikoeru-project/kikoeru-quasar.git`.

### 1. npm install (multiple workarounds needed)

```sh
cd "$SRC"
npm install \
  --no-audit --no-fund \
  --registry https://registry.npmjs.org/ \
  --ignore-scripts \
  --legacy-peer-deps
```

Each flag is necessary:
- `--registry`: the default (Taobao mirror) has expired certs in 2026
- `--ignore-scripts`: skips `zlib@1.0.5`'s `node-waf build` (no node-waf
  in modern Node) and any other broken native compile steps
- `--legacy-peer-deps`: the 2020-era deps don't satisfy modern peer
  ranges; npm 7+ would otherwise refuse

If `--no-save` packages are added later (e.g. `sass@1.32.13` or
`terser@5`), they may pull `node-sass` back in via the dependency
graph. Rename it after each install:

```sh
[ -d node_modules/node-sass ] && mv node_modules/node-sass node_modules/.node-sass-hidden
```

### 2. Install Dart Sass as a fallback (replaces node-sass)

node-sass@4.x has no prebuilt binaries for Node 22 arm64. The
sass-loader@8 default implementation tries node-sass first, falls back
to `sass` if node-sass can't be resolved. We want the latter.

```sh
npm install --no-save --ignore-scripts --legacy-peer-deps sass@1.32.13
```

The `--no-save` keeps `package.json` clean (we don't actually want to
ship with sass; this is a local build fix).

If `node_modules/node-sass` reappears (npm install of unrelated deps
may regenerate it), rename again: `mv node_modules/node-sass …hidden`.

### 3. Patch `inject.style-rules.js`

The Quasar 1.x framework passes `outputStyle: "nested"` to sass-loader.
Dart Sass removed `"nested"` in favor of `"expanded" / "compressed" / "compact"`.

```diff
--- a/node_modules/@quasar/app/lib/webpack/inject.style-rules.js
+++ b/node_modules/@quasar/app/lib/webpack/inject.style-rules.js
@@ -120,11 +120,11 @@
     ...pref.stylusLoaderOptions
   })
   injectRule(chain, pref, 'scss', /\.scss$/, 'sass-loader', merge(
-    { sassOptions: { outputStyle: /* required for RTL */ 'nested' } },
+    { sassOptions: { outputStyle: /* patched for Dart Sass */ 'expanded' } },
     pref.scssLoaderOptions
   )),
   injectRule(chain, pref, 'sass', /\.sass$/, 'sass-loader', merge(
-    { sassOptions: { indentedSyntax: true, outputStyle: /* required for RTL */ 'nested' } },
+    { sassOptions: { indentedSyntax: true, outputStyle: /* patched for Dart Sass */ 'expanded' } },
     pref.sassLoaderOptions
   ))
```

Setting `scssLoaderOptions` in `quasar.conf.js` does NOT override
this — `merge` from lodash deep-merges but the framework's hardcoded
`outputStyle` wins. Patch the file directly.

### 4. Disable minification in `quasar.conf.js`

vue-plyr@6.0.4 ships a `.mjs` with TypeScript `!` non-null assertions
that terser 4.x (the version pulled by `terser-webpack-plugin@1`) can't
parse. Upgrading terser doesn't help (terser-webpack-plugin bundles
its own). The simplest fix is to skip minification entirely; the
output is ~5MB instead of ~1.5MB.

```diff
--- a/quasar.conf.js
+++ b/quasar.conf.js
@@ -71,6 +71,7 @@
     // Full list of options: …
     build: {
       vueRouterMode: 'history',
+      minify: false, // patched: old terser can't parse vue-plyr's TS syntax
```

### 5. Shim `src/boot/plyr.js` to avoid vue-plyr@6 (with seekable progress bar)

Even with minification off, webpack still needs to RESOLVE `vue-plyr`,
which fails because vue-plyr@6.0.4 has a non-existent `package.json`
field that breaks webpack's resolution. Replace the boot file with a
vanilla `<audio>` shim that:

1. Exposes the Plyr-compatible `this.$refs.plyr.player` API that
   kikoeru's `AudioElement.vue` calls (`player.play()`, `.pause()`,
   `.rewind(sec)`, `.forward(sec)`, `.currentTime`, `.duration`,
   `.muted`, `.volume`, `.media`).
2. Renders its **own seekable progress bar** below the `<audio>` —
   the kikoeru AudioPlayer component does NOT render its own slider,
   so without the bar there's no way to seek the audio.
3. Forwards all media events (`canplay`, `timeupdate`, `ended`,
   `seeked`, `playing`, `waiting`, `pause`, plus `durationchange`,
   `progress`, `loadeddata` for the bar) to Vue so kikoeru's
   `@canplay`, `@timeupdate`, etc. handlers fire.

**Don't** leave the unused `options` parameter — ESLint (configured
in the kikoeru project) rejects it as `no-unused-vars` and the build
fails before reaching webpack.

The shim (this is what the in-tree `src/boot/plyr.js` currently
contains — copy verbatim):

```js
import Vue from 'vue'

const audioEvents = ['canplay', 'timeupdate', 'ended', 'seeked',
  'playing', 'waiting', 'pause', 'durationchange', 'progress',
  'loadeddata']

const VuePlyr = {
  install(Vue) {
    Vue.component('vue-plyr', {
      props: { emit: { type: Array, default: () => [] } },
      data() {
        return { currentTime: 0, duration: 0, bufferedEnd: 0, seeking: false }
      },
      computed: {
        progressPct() {
          if (!this.duration || this.duration <= 0) return 0
          return Math.min(100, (this.currentTime / this.duration) * 100)
        },
        bufferedPct() {
          if (!this.duration || this.duration <= 0) return 0
          return Math.min(100, (this.bufferedEnd / this.duration) * 100)
        },
      },
      methods: {
        _audio() { return this.$refs.audio || null },
        _attachListeners(audio) {
          audioEvents.forEach(evt => {
            audio.addEventListener(evt, () => {
              if (['timeupdate', 'durationchange', 'canplay',
                   'loadeddata', 'seeked'].includes(evt)) {
                if (!this.seeking) this.currentTime = audio.currentTime || 0
                this.duration = (isFinite(audio.duration) && audio.duration > 0)
                  ? audio.duration : 0
              } else if (evt === 'progress') {
                if (audio.buffered && audio.buffered.length > 0) {
                  this.bufferedEnd = audio.buffered.end(audio.buffered.length - 1)
                }
              }
              this.$emit(evt, evt)
            })
          })
        },
        _onSeekInput(e) {
          this.seeking = true
          this.currentTime = parseFloat(e.target.value) || 0
        },
        _onSeekChange(e) {
          const t = parseFloat(e.target.value) || 0
          const a = this._audio()
          if (a) a.currentTime = t
          this.currentTime = t
          this.seeking = false
          this.$emit('seeked', t)
        },
      },
      render(h) {
        // Pass through the slot's <audio>, then add a progress bar
        return h('div', { class: 'vue-plyr-shim',
                          style: 'display:block; width:100%' }, [
          ...(this.$slots.default || []),
          h('div', { class: 'vue-plyr-shim-bar',
                    style: 'position:relative; height:18px; margin-top:6px;' }, [
            h('div', { style: 'position:absolute; top:7px; left:0; right:0; '
              + 'height:4px; background:#e0e0e0; border-radius:2px;' }),
            h('div', { style: {
                position: 'absolute', top: '7px', left: 0, height: '4px',
                background: '#bdbdbd', borderRadius: '2px',
                width: `${this.bufferedPct}%`, transition: 'width 0.2s' } }),
            h('div', { style: {
                position: 'absolute', top: '7px', left: 0, height: '4px',
                background: '#1976d2', borderRadius: '2px',
                width: `${this.progressPct}%`,
                transition: this.seeking ? 'none' : 'width 0.15s linear' } }),
            h('input', {
              class: 'vue-plyr-shim-range',
              attrs: {
                type: 'range', min: '0',
                max: this.duration > 0 ? String(this.duration) : '0.001',
                step: '0.01', value: String(this.currentTime),
                'aria-label': 'Seek',
              },
              style: {
                position: 'absolute', top: '0', left: '0', right: '0',
                width: '100%', height: '18px', margin: 0,
                opacity: 0, cursor: 'pointer',
              },
              on: { input: this._onSeekInput, change: this._onSeekChange },
            }),
          ]),
        ])
      },
      mounted() {
        const audio = this.$el ? this.$el.querySelector('audio') : null
        if (!audio) return
        this.$refs.audio = audio
        this._attachListeners(audio)
        this.currentTime = audio.currentTime || 0
        this.duration = (isFinite(audio.duration) && audio.duration > 0)
          ? audio.duration : 0
        if (audio.buffered && audio.buffered.length > 0) {
          this.bufferedEnd = audio.buffered.end(audio.buffered.length - 1)
        }
        const player = {
          get media() { return audio },
          get duration() { return audio.duration || 0 },
          get currentTime() { return audio.currentTime || 0 },
          get muted() { return audio.muted },
          set muted(v) { audio.muted = v },
          get volume() { return audio.volume },
          set volume(v) { audio.volume = v },
          play() { return audio.play() },
          pause() { return audio.pause() },
          rewind(sec) {
            if (audio.currentTime) audio.currentTime =
              Math.max(0, audio.currentTime - sec) },
          forward(sec) { audio.currentTime =
            Math.min(audio.duration || 0, audio.currentTime + sec) },
        }
        this.player = player
      },
    })
  },
}

Vue.use(VuePlyr)
```

**Common shim bugs to avoid:**

- Forgetting `durationchange` / `progress` / `loadeddata` in the
  event list — the bar won't update for slow-loading audio.
- Setting `max` to `0` instead of `'0.001'` when duration isn't
  known — Chromium's `<input type="range">` refuses to render a
  0-0 slider and the bar becomes invisible.
- Emitting `$emit('seeked', evt)` (the event object) instead of
  `$emit('seeked', t)` (the timestamp) — kikoeru's
  `AudioElement.onSeeked` ignores the arg, so this is technically
  harmless, but other Vue components may not.
- Not calling `this.$emit(evt, evt)` for ALL events kikoeru listens
  to — the `play`/`pause` events in particular are how the
  AudioElement's `playLrc()` toggles the lyric scroll. Missing
  those = LRC won't sync.

### 6. Run the build

```sh
NODE_OPTIONS=--openssl-legacy-provider ./node_modules/.bin/quasar build
```

`--openssl-legacy-provider` is needed for webpack 4's MD4 hash
function (OpenSSL 3+ in Node 17+ requires this opt-in). Without it:
`Error: error:0308010C:digital envelope routines::unsupported`.

The output is in `dist/spa/`. Copy to `<ASMR_STACK_ROOT>/kikoeru-spa/`:

```sh
rm -rf <ASMR_STACK_ROOT>/kikoeru-spa
cp -r dist/spa <ASMR_STACK_ROOT>/kikoeru-spa
```

asmr-view auto-detects the kikoeru SPA at `<ASMR_STACK_ROOT>/kikoeru-spa/index.html`
and serves it at `/` instead of the hand-rolled SPA. No flag needed.

## What the build produces

- `dist/spa/index.html` (1.3 KB shell)
- `dist/spa/css/app.<hash>.css` (~3 MB unminified Quasar CSS)
- `dist/spa/js/vendor.<hash>.js` (vendor bundle, mostly plyr)
- `dist/spa/js/app.<hash>.js` (app code)
- `dist/spa/js/runtime.<hash>.js` (webpack runtime)
- `dist/spa/fonts/`, `dist/spa/statics/` (icon font, favicons)

Total: ~5 MB.

## Common failure modes and what they actually mean

| Symptom | Root cause | Fix |
|---|---|---|
| `CERT_HAS_EXPIRED` from npm | Taobao mirror certs expired | `--registry https://registry.npmjs.org/` |
| `node-waf: command not found` | `zlib@1.0.5` prebuild script | `--ignore-scripts` |
| `Node Sass does not yet support… (arm64, runtime 127)` | No Node 22 arm64 binaries for node-sass 4 | rename `node_modules/node-sass`, install `sass@1.32.13` |
| `Invalid argument(s): Unsupported output style "nested"` | Dart Sass removed 'nested' | patch `inject.style-rules.js` (step 3) |
| `Error: error:0308010C:digital envelope routines::unsupported` | webpack 4 + OpenSSL 3 | `NODE_OPTIONS=--openssl-legacy-provider` |
| `Unexpected token: operator (!)` in vue-plyr.mjs | terser 4 can't parse TS `!` non-null assertions | shim `src/boot/plyr.js` (step 5) + `minify: false` (step 4) |
| `Can't resolve 'plyr' in vue-plyr/dist` | vue-plyr's package.json lacks `browser` field | resolved by shimming (step 5) |
| `Module not found: Error: Can't resolve 'node-sass'` | npm install regenerated the node-sass dir | rename it again (see step 1) |
| `'options' is defined but never used` | ESLint blocks build | remove unused `options` param from your shim (step 5) |

## Static-asset routing requirement

The kikoeru SPA uses absolute paths (`/js/vendor.86022408.js`,
`/css/app.88bd61a4.css`, `/statics/icons/...`). asmr-view only
serves `/index.html` and `/api/*` by default — **you need to add a
static-file fallback** in the dispatch that serves
`<ASMR_STACK_ROOT>/kikoeru-spa/{js,css,statics,fonts}/<path>` for
any matching path. Without it the SPA shell loads but every asset
404s, leaving a blank page.

The fallback is roughly:

```python
SPA_STATIC_SUBDIRS = ("js", "css", "statics", "fonts")
def _serve_kikoeru_static(self, sub, rest):
    if sub in SPA_STATIC_SUBDIRS and ".." not in rest:
        path = (KIKOERU_SPA_DIR / sub / rest).resolve()
        if str(path).startswith(str(KIKOERU_SPA_DIR.resolve())) and path.is_file():
            # stream file with correct Content-Type
            ...
```

Add a new branch to `_dispatch` before the catch-all 404:
`elif any(path.startswith(f"/{s}/") for s in SPA_STATIC_SUBDIRS): ...`.

## How long this should take

~20 minutes if you've done it before, ~1 hour cold. The `node_modules`
rebuild is the slow part (~30s); the actual `quasar build` is fast
(~5s once it gets past SCSS).

If a step fails, check the table above before searching the web —
the error messages are misleading.
