(function () {
  var state = {
    hash: '',
    workId: '',
    subtitleHash: '',
    subtitleTitle: '',
    lines: [],
    activeIndex: -1,
    offset: 0,
    open: false,
    loading: false,
    loadToken: 0,
    lastCommittedLyric: null
  }

  var els = {}
  var OFFSET_STEP = 0.3
  var OFFSET_LIMIT = 30

  function getStore () {
    var root = document.getElementById('q-app')
    var vm = root && root.__vue__
    return vm && vm.$store
  }

  function getCurrentTrack () {
    var store = getStore()
    if (store && store.getters) {
      return store.getters['AudioPlayer/currentPlayingFile'] || null
    }
    return null
  }

  function getAudio () {
    return document.querySelector('audio')
  }

  function getAudioHashFromDom () {
    var source = document.querySelector('audio source[src*="/api/media/stream/"]')
    var audio = document.querySelector('audio[src*="/api/media/stream/"]')
    var src = source ? source.getAttribute('src') : (audio && audio.getAttribute('src'))
    if (!src) return ''
    try {
      var url = new URL(src, window.location.href)
      var prefix = '/api/media/stream/'
      if (url.pathname.indexOf(prefix) !== 0) return ''
      return decodeURIComponent(url.pathname.slice(prefix.length))
    } catch (err) {
      var match = src.match(/\/api\/media\/stream\/([^?#]+)/)
      return match ? decodeURIComponent(match[1]) : ''
    }
  }

  function currentHash () {
    var track = getCurrentTrack()
    return (track && track.hash) || getAudioHashFromDom()
  }

  function normalizeWorkId (value) {
    var raw = String(value || '').trim()
    if (!raw) return ''
    var first = raw.split('/')[0]
    if (/^RJ\d+$/i.test(first)) return first.toUpperCase()
    if (/^\d+$/.test(first)) return first
    return ''
  }

  function currentWorkId (track, hash) {
    return normalizeWorkId(track && (
      track.rj_id ||
      track.rjId ||
      track.work_rj ||
      track.workId ||
      track.work_id
    )) || normalizeWorkId(hash)
  }

  function tokenQuery () {
    var token = ''
    try {
      token = window.localStorage.getItem('jwt-token') || ''
    } catch (err) {}
    return '?token=' + encodeURIComponent(token)
  }

  function storageKey () {
    var work = state.workId || 'unknown-work'
    var hash = state.hash || 'unknown-track'
    return 'asmrLyricsOffset:' + work + ':' + hash
  }

  function loadOffset () {
    try {
      var raw = window.localStorage.getItem(storageKey())
      var value = Number(raw)
      return Number.isFinite(value) ? clampOffset(value) : 0
    } catch (err) {
      return 0
    }
  }

  function saveOffset () {
    try {
      window.localStorage.setItem(storageKey(), String(roundOffset(state.offset)))
    } catch (err) {}
  }

  function clampOffset (value) {
    value = Number(value)
    if (!Number.isFinite(value)) return 0
    return Math.max(-OFFSET_LIMIT, Math.min(OFFSET_LIMIT, value))
  }

  function roundOffset (value) {
    return Math.round(clampOffset(value) * 10) / 10
  }

  function parseOffsetInput (value) {
    var match = String(value || '').trim().match(/[-+]?\d+(?:\.\d+)?/)
    return match ? roundOffset(Number(match[0])) : state.offset
  }

  function formatOffset (value) {
    value = roundOffset(value)
    return (value > 0 ? '+' : '') + value.toFixed(1) + 's'
  }

  function formatTime (seconds) {
    seconds = Math.max(0, Number(seconds) || 0)
    var total = Math.floor(seconds)
    var min = Math.floor(total / 60)
    var sec = total % 60
    var cs = Math.floor((seconds - total) * 100)
    return '[' + String(min).padStart(2, '0') + ':' + String(sec).padStart(2, '0') + '.' + String(cs).padStart(2, '0') + ']'
  }

  function fractionToSeconds (raw) {
    if (!raw) return 0
    if (raw.length === 1) return Number(raw) / 10
    if (raw.length === 2) return Number(raw) / 100
    return Number(raw.slice(0, 3).padEnd(3, '0')) / 1000
  }

  function parseLrc (text) {
    var out = []
    String(text || '').split(/\r?\n/).forEach(function (line, row) {
      var matches = Array.from(line.matchAll(/\[(\d+):(\d{1,2})(?:[.:](\d{1,3}))?\]/g))
      if (!matches.length) return
      var body = line.replace(/(?:\[\d+:\d{1,2}(?:[.:]\d{1,3})?\])+/g, '').trim()
      matches.forEach(function (match) {
        var min = Number(match[1])
        var sec = Number(match[2])
        if (!Number.isFinite(min) || !Number.isFinite(sec)) return
        out.push({
          time: min * 60 + sec + fractionToSeconds(match[3] || ''),
          text: body,
          row: row
        })
      })
    })
    return out.sort(function (a, b) {
      if (a.time === b.time) return a.row - b.row
      return a.time - b.time
    })
  }

  function lineAtTime (seconds) {
    var idx = -1
    var target = seconds + 0.03
    for (var i = 0; i < state.lines.length; i++) {
      if (state.lines[i].time <= target) idx = i
      else break
    }
    return idx
  }

  function activeLyricText () {
    var audio = getAudio()
    if (!audio || !state.lines.length) return ''
    var idx = lineAtTime((audio.currentTime || 0) + state.offset)
    return idx >= 0 ? state.lines[idx].text : ''
  }

  function commitCurrentLyric () {
    var store = getStore()
    if (!store || !store.commit) return
    var text = activeLyricText()
    if (text === state.lastCommittedLyric) return
    state.lastCommittedLyric = text
    store.commit('AudioPlayer/SET_CURRENT_LYRIC', text)
  }

  function seekToLine (line) {
    var audio = getAudio()
    if (!audio || !line) return
    audio.currentTime = Math.max(0, line.time - state.offset)
    if (typeof audio.play === 'function' && audio.paused) {
      audio.play().catch(function () {})
    }
    updateActiveLine(true)
  }

  function ensureStyles () {
    if (document.getElementById('asmr-lyrics-panel-style')) return
    var style = document.createElement('style')
    style.id = 'asmr-lyrics-panel-style'
    style.textContent = [
      '#lyricsBar{pointer-events:none!important;}',
      '.audio-player.asmr-player-layout{overflow:visible;}',
      '.audio-player.asmr-player-layout .albumart>.row.absolute.q-pl-md.q-pr-md.col-12.justify-between{display:none!important;}',
      '.audio-player.asmr-player-layout .asmr-player-transport-row{height:62px!important;display:grid!important;grid-template-columns:55px 55px 65px 55px 55px!important;align-items:center!important;justify-content:center!important;gap:12px!important;padding:0 18px!important;}',
      '.audio-player.asmr-player-layout .asmr-player-transport-row>.q-btn{min-width:0!important;justify-self:center!important;}',
      '.audio-player.asmr-player-layout .asmr-player-original-hidden{display:none!important;}',
      '.asmr-player-menu-hidden{display:none!important;}',
      '.asmr-player-control-btn,.asmr-player-utility-btn,.asmr-lyrics-preview-toggle{border:0;background:transparent;color:rgba(0,0,0,.87);display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;border-radius:4px;font:inherit;line-height:1;}',
      '.asmr-player-control-btn{width:55px;height:55px;}',
      '.asmr-player-control-btn--primary{width:65px;height:55px;font-size:28px;}',
      '.asmr-player-utility-row{height:45px;display:grid;grid-template-columns:repeat(4,45px);align-items:center;justify-content:center;gap:20px;padding:0 20px;background:rgba(0,0,0,.035);}',
      '.asmr-player-utility-btn,.asmr-lyrics-preview-toggle{width:45px;height:45px;}',
      '.asmr-player-control-btn:hover,.asmr-player-utility-btn:hover,.asmr-lyrics-preview-toggle:hover{background:rgba(0,0,0,.06);}',
      '.asmr-player-control-btn__icon,.asmr-player-utility-btn__icon,.asmr-lyrics-preview-toggle__icon{font-family:"Material Icons";font-size:24px;line-height:1;font-weight:normal;font-style:normal;}',
      '.asmr-player-control-btn--primary .asmr-player-control-btn__icon{font-size:32px;}',
      '.asmr-lyrics-preview-toggle[aria-pressed="true"]{background:rgba(0,0,0,.12);color:#000;}',
      '.asmr-lyrics-scrim{position:fixed;inset:0;z-index:100024;background:rgba(0,0,0,.42);}',
      '.asmr-lyrics-panel{position:fixed;left:0;top:0;bottom:0;z-index:100025;width:min(555px,calc(100vw - 16px));background:#fff;color:rgba(0,0,0,.9);box-shadow:4px 0 18px rgba(0,0,0,.32);display:flex;flex-direction:column;font-family:Roboto,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}',
      '.asmr-lyrics-scrim[hidden],.asmr-lyrics-panel[hidden]{display:none!important;}',
      '.asmr-lyrics-panel__bar{height:58px;min-height:58px;border-bottom:1px solid #e0e0e0;display:flex;align-items:center;gap:10px;padding:9px 11px;}',
      '.asmr-lyrics-panel__select{max-width:calc(100% - 52px);height:40px;border:1px solid #d0d0d0;border-radius:4px;background:#fff;color:rgba(0,0,0,.85);font:500 14px/1.2 Roboto,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:0 32px 0 12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}',
      '.asmr-lyrics-panel__close{margin-left:auto;width:40px;height:40px;border:0;border-radius:4px;background:transparent;color:#000;font-size:30px;line-height:40px;cursor:pointer;}',
      '.asmr-lyrics-panel__close:hover{background:rgba(0,0,0,.06);}',
      '.asmr-lyrics-panel__status{padding:24px;color:rgba(0,0,0,.58);font-size:14px;}',
      '.asmr-lyrics-panel__list{flex:1;overflow:auto;padding:12px 11px 18px;}',
      '.asmr-lyrics-line{width:100%;border:0;background:transparent;color:#000;text-align:left;border-radius:0;cursor:pointer;padding:9px 16px 8px;margin:0 0 2px;min-height:48px;font:500 14px/1.42 Roboto,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}',
      '.asmr-lyrics-line:hover{background:#f3f3f3;}',
      '.asmr-lyrics-line__time{display:block;color:#6f7282;font-size:12px;font-weight:500;line-height:1.2;margin-bottom:3px;}',
      '.asmr-lyrics-line__text{display:block;white-space:pre-wrap;overflow-wrap:anywhere;}',
      '.asmr-lyrics-line--active{background:#f0e1f1;color:#8e24aa;}',
      '.asmr-lyrics-line--active:hover{background:#ead7ec;}',
      '.asmr-lyrics-line--active .asmr-lyrics-line__time{color:#8e24aa;}',
      '.asmr-lyrics-panel__shift{min-height:39px;border-top:1px solid #ddd;background:#fff;display:grid;grid-template-columns:minmax(92px,1fr) 72px 72px 72px;align-items:center;gap:8px;padding:6px 10px;}',
      '.asmr-lyrics-panel__shift button{height:28px;border:0;border-radius:4px;background:transparent;color:#000;font:700 14px/1 Roboto,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;cursor:pointer;padding:0 8px;}',
      '.asmr-lyrics-panel__shift button:hover{background:rgba(0,0,0,.06);}',
      '.asmr-lyrics-panel__shift input{height:30px;width:100%;box-sizing:border-box;border:1px solid #cfcfcf;border-radius:4px;text-align:center;color:#333;background:#fff;font:500 14px/1 Roboto,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:0 6px;}',
      '@media (max-width:640px){body.asmr-player-open #lyricsBar{display:none!important;}.asmr-lyrics-panel{width:100vw;right:0;}.asmr-lyrics-panel__shift{grid-template-columns:1fr 64px 68px 64px;gap:4px;padding:6px;}.asmr-lyrics-line{padding-left:12px;padding-right:12px;}.audio-player.asmr-player-layout .albumart{height:calc(100% - 275px)!important;}.asmr-player-transport-row{grid-template-columns:48px 48px 60px 48px 48px!important;gap:8px!important;padding:0 8px!important;}.asmr-player-utility-row{grid-template-columns:repeat(4,42px);gap:14px;padding:0 8px;}.asmr-player-control-btn{width:48px;}.asmr-player-control-btn--primary{width:60px;}.asmr-player-utility-btn,.asmr-lyrics-preview-toggle{width:42px;}}'
    ].join('')
    document.head.appendChild(style)
  }

  function buildPanel () {
    if (els.panel) return
    ensureStyles()

    els.scrim = document.createElement('div')
    els.scrim.className = 'asmr-lyrics-scrim'
    els.scrim.hidden = true
    els.scrim.addEventListener('click', closePanel)

    els.panel = document.createElement('aside')
    els.panel.className = 'asmr-lyrics-panel'
    els.panel.hidden = true
    els.panel.setAttribute('role', 'dialog')
    els.panel.setAttribute('aria-modal', 'true')
    els.panel.setAttribute('aria-label', 'Lyrics preview')

    var bar = document.createElement('div')
    bar.className = 'asmr-lyrics-panel__bar'

    els.select = document.createElement('select')
    els.select.className = 'asmr-lyrics-panel__select'
    els.select.setAttribute('aria-label', 'Subtitle file')

    els.close = document.createElement('button')
    els.close.type = 'button'
    els.close.className = 'asmr-lyrics-panel__close'
    els.close.setAttribute('aria-label', 'Close lyrics preview')
    els.close.textContent = 'x'
    els.close.addEventListener('click', closePanel)

    els.status = document.createElement('div')
    els.status.className = 'asmr-lyrics-panel__status'
    els.status.hidden = true

    els.list = document.createElement('div')
    els.list.className = 'asmr-lyrics-panel__list'

    var shift = document.createElement('div')
    shift.className = 'asmr-lyrics-panel__shift'

    els.reset = document.createElement('button')
    els.reset.type = 'button'
    els.reset.textContent = '重置偏移'
    els.reset.addEventListener('click', function () { setOffset(0) })

    els.minus = document.createElement('button')
    els.minus.type = 'button'
    els.minus.textContent = '-0.3s'
    els.minus.addEventListener('click', function () { setOffset(state.offset - OFFSET_STEP) })

    els.offsetInput = document.createElement('input')
    els.offsetInput.type = 'text'
    els.offsetInput.inputMode = 'decimal'
    els.offsetInput.setAttribute('aria-label', 'Lyrics offset')
    els.offsetInput.addEventListener('change', function () {
      setOffset(parseOffsetInput(els.offsetInput.value))
    })
    els.offsetInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault()
        setOffset(parseOffsetInput(els.offsetInput.value))
        els.offsetInput.blur()
      }
    })

    els.plus = document.createElement('button')
    els.plus.type = 'button'
    els.plus.textContent = '+0.3s'
    els.plus.addEventListener('click', function () { setOffset(state.offset + OFFSET_STEP) })

    bar.appendChild(els.select)
    bar.appendChild(els.close)
    shift.appendChild(els.reset)
    shift.appendChild(els.minus)
    shift.appendChild(els.offsetInput)
    shift.appendChild(els.plus)
    els.panel.appendChild(bar)
    els.panel.appendChild(els.status)
    els.panel.appendChild(els.list)
    els.panel.appendChild(shift)
    document.body.appendChild(els.scrim)
    document.body.appendChild(els.panel)
  }

  function renderSelect () {
    if (!els.select) return
    var title = state.subtitleTitle || (state.subtitleHash ? state.subtitleHash.replace(/@lrc$/, '') : 'Lyrics')
    els.select.innerHTML = ''
    var option = document.createElement('option')
    option.textContent = title
    option.value = state.subtitleHash || title
    els.select.appendChild(option)
  }

  function renderLines () {
    buildPanel()
    renderSelect()
    els.list.innerHTML = ''
    els.status.hidden = true

    if (state.loading) {
      els.status.hidden = false
      els.status.textContent = '歌词读取中...'
      return
    }

    if (!state.hash) {
      els.status.hidden = false
      els.status.textContent = '未播放音频'
      return
    }

    if (!state.lines.length) {
      els.status.hidden = false
      els.status.textContent = '当前音频没有可预览的歌词'
      return
    }

    state.lines.forEach(function (line, index) {
      var row = document.createElement('button')
      row.type = 'button'
      row.className = 'asmr-lyrics-line'
      row.dataset.index = String(index)
      row.addEventListener('click', function () { seekToLine(line) })

      var time = document.createElement('span')
      time.className = 'asmr-lyrics-line__time'
      time.textContent = formatTime(line.time)

      var text = document.createElement('span')
      text.className = 'asmr-lyrics-line__text'
      text.textContent = line.text || ' '

      row.appendChild(time)
      row.appendChild(text)
      els.list.appendChild(row)
    })
    updateActiveLine(false)
  }

  function setOffset (value) {
    state.offset = roundOffset(value)
    saveOffset()
    updateOffsetInput()
    commitCurrentLyric()
    updateActiveLine(true)
  }

  function updateOffsetInput () {
    if (els.offsetInput) els.offsetInput.value = formatOffset(state.offset)
  }

  function updateActiveLine (scrollIntoView) {
    if (!els.list || !state.lines.length) {
      state.activeIndex = -1
      commitCurrentLyric()
      return
    }
    var audio = getAudio()
    var time = (audio ? audio.currentTime || 0 : 0) + state.offset
    var next = lineAtTime(time)
    if (next === state.activeIndex) {
      commitCurrentLyric()
      return
    }
    var oldRow = els.list.querySelector('.asmr-lyrics-line--active')
    if (oldRow) oldRow.classList.remove('asmr-lyrics-line--active')
    state.activeIndex = next
    if (next >= 0) {
      var row = els.list.querySelector('[data-index="' + next + '"]')
      if (row) {
        row.classList.add('asmr-lyrics-line--active')
        if (scrollIntoView && state.open) {
          row.scrollIntoView({ block: 'center', behavior: 'smooth' })
        }
      }
    }
    commitCurrentLyric()
  }

  function openPanel () {
    buildPanel()
    state.open = true
    els.scrim.hidden = false
    els.panel.hidden = false
    updateTogglePressed()
    renderLines()
    updateOffsetInput()
    updateActiveLine(true)
  }

  function closePanel () {
    state.open = false
    if (els.scrim) els.scrim.hidden = true
    if (els.panel) els.panel.hidden = true
    updateTogglePressed()
  }

  function togglePanel () {
    state.open ? closePanel() : openPanel()
  }

  function loadSubtitleTitle (hash, token) {
    var clean = String(hash || '').replace(/@lrc$/, '')
    if (!clean) return Promise.resolve('')
    return fetch('/api/track/' + encodeURIComponent(clean) + token)
      .then(function (res) { return res.ok ? res.json() : null })
      .then(function (track) { return (track && track.title) || clean })
      .catch(function () { return clean })
  }

  function loadTrackMeta (hash, track, token) {
    if (currentWorkId(track, hash)) return Promise.resolve(track || {})
    return fetch('/api/track/' + encodeURIComponent(hash) + token)
      .then(function (res) { return res.ok ? res.json() : null })
      .then(function (meta) { return meta || track || {} })
      .catch(function () { return track || {} })
  }

  function loadLyricsForCurrentTrack () {
    var hash = currentHash()
    var track = getCurrentTrack()
    if (!hash || hash === state.hash) return

    state.hash = hash
    state.workId = currentWorkId(track, hash)
    state.subtitleHash = ''
    state.subtitleTitle = ''
    state.lines = []
    state.activeIndex = -1
    state.offset = loadOffset()
    state.loading = true
    state.lastCommittedLyric = null
    updateOffsetInput()
    renderLines()

    var myToken = ++state.loadToken
    var token = tokenQuery()
    loadTrackMeta(hash, track, token)
      .then(function (meta) {
        if (myToken !== state.loadToken) return null
        state.workId = currentWorkId(meta, hash) || state.workId
        state.offset = loadOffset()
        updateOffsetInput()
        return fetch('/api/media/check-lrc/' + hash + token)
      })
      .then(function (res) {
        if (!res) return null
        if (!res.ok) throw new Error(res.status + ' ' + res.statusText)
        return res.json()
      })
      .then(function (check) {
        if (!check) return null
        if (myToken !== state.loadToken) return null
        if (!check || !check.result || !check.hash) return { missing: true }
        state.subtitleHash = check.hash
        return Promise.all([
          fetch('/api/media/stream/' + check.hash + token).then(function (res) {
            if (!res.ok) throw new Error(res.status + ' ' + res.statusText)
            return res.text()
          }),
          loadSubtitleTitle(check.hash, token)
        ])
      })
      .then(function (result) {
        if (myToken !== state.loadToken || !result) return
        state.loading = false
        if (result.missing) {
          state.lines = []
          state.subtitleTitle = ''
        } else {
          state.lines = parseLrc(result[0])
          state.subtitleTitle = result[1] || ''
        }
        renderLines()
        commitCurrentLyric()
      })
      .catch(function (err) {
        if (myToken !== state.loadToken) return
        state.loading = false
        state.lines = []
        state.subtitleTitle = ''
        console.warn('ASMR lyrics preview failed:', err)
        renderLines()
        commitCurrentLyric()
      })
  }

  function updateTogglePressed () {
    var btn = document.getElementById('asmr-lyrics-preview-toggle')
    if (btn) btn.setAttribute('aria-pressed', state.open ? 'true' : 'false')
  }

  function createIconButton (id, icon, title, className, onClick) {
    var btn = document.getElementById(id)
    if (!btn) {
      btn = document.createElement('button')
      btn.id = id
      btn.type = 'button'
      btn.addEventListener('click', function (event) {
        event.preventDefault()
        event.stopPropagation()
        onClick()
      })
    }
    if (btn.className !== className) btn.className = className
    if (btn.title !== title) btn.title = title
    if (btn.getAttribute('aria-label') !== title) btn.setAttribute('aria-label', title)
    var iconClass = className.indexOf('asmr-player-control-btn') >= 0
      ? 'asmr-player-control-btn__icon'
      : 'asmr-player-utility-btn__icon'
    var span = btn.firstElementChild
    if (!span || span.tagName !== 'SPAN') {
      btn.textContent = ''
      span = document.createElement('span')
      btn.appendChild(span)
    }
    if (span.className !== iconClass) span.className = iconClass
    if (span.textContent !== icon) span.textContent = icon
    return btn
  }

  function seekBy (delta) {
    var audio = getAudio()
    if (!audio) return
    var duration = Number(audio.duration)
    var max = Number.isFinite(duration) && duration > 0 ? duration : Infinity
    audio.currentTime = Math.max(0, Math.min(max, (audio.currentTime || 0) + delta))
    var store = getStore()
    if (store && store.commit) store.commit('AudioPlayer/SET_CURRENT_TIME', audio.currentTime)
    updateActiveLine(false)
  }

  function commitAudioPlayer (mutation) {
    var store = getStore()
    if (store && store.commit) store.commit('AudioPlayer/' + mutation)
  }

  function clickNode (node) {
    if (node && typeof node.click === 'function') node.click()
  }

  function isVisible (node) {
    if (!node) return false
    var style = window.getComputedStyle(node)
    var rect = node.getBoundingClientRect()
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
  }

  function tagOriginalControls (row) {
    var existing = Array.from(row.children).filter(function (node) {
      return node.nodeType === 1 &&
        !node.classList.contains('asmr-player-control-btn') &&
        !node.classList.contains('asmr-player-utility-btn') &&
        !node.classList.contains('asmr-lyrics-preview-toggle') &&
        !node.classList.contains('asmr-player-utility-row')
    })
    if (row.dataset.asmrPlayerTagged !== '1' && existing.length >= 5) {
      existing[0].dataset.asmrPlayerRole = 'queue'
      existing[1].dataset.asmrPlayerRole = 'previous'
      existing[2].dataset.asmrPlayerRole = 'play'
      existing[3].dataset.asmrPlayerRole = 'next'
      existing[4].dataset.asmrPlayerRole = 'mode'
      row.dataset.asmrPlayerTagged = '1'
    }
    var roles = {}
    Array.from(row.children).forEach(function (node) {
      if (node.dataset && node.dataset.asmrPlayerRole) {
        roles[node.dataset.asmrPlayerRole] = node
      }
    })
    return roles
  }

  function syncMoreMenu () {
    Array.from(document.querySelectorAll('.q-menu .q-item')).forEach(function (item) {
      var text = String(item.innerText || item.textContent || '').replace(/\s+/g, '').trim()
      if (text.indexOf('交换进度按钮与切换按钮') !== -1) {
        item.classList.add('asmr-player-menu-hidden')
        item.setAttribute('aria-hidden', 'true')
      }
    })
  }

  function syncToggleButton () {
    ensureStyles()
    var row = document.querySelector('.audio-player > .row.justify-around')
    if (!row) {
      document.body.classList.remove('asmr-player-open')
      return
    }
    var player = row.closest('.audio-player')
    if (player) {
      player.classList.add('asmr-player-layout')
      document.body.classList.toggle('asmr-player-open', isVisible(player))
    }
    row.classList.add('asmr-player-transport-row')

    var roles = tagOriginalControls(row)
    ;['queue', 'previous', 'next', 'mode'].forEach(function (role) {
      if (roles[role]) roles[role].classList.add('asmr-player-original-hidden')
    })
    if (roles.play) {
      roles.play.classList.remove('asmr-player-original-hidden')
      roles.play.classList.add('asmr-player-control-btn', 'asmr-player-control-btn--primary')
      roles.play.style.order = '3'
    }

    var prev = createIconButton('asmr-player-prev-track', 'skip_previous', 'Previous track', 'asmr-player-control-btn', function () {
      commitAudioPlayer('PREVIOUS_TRACK')
    })
    var rewind = createIconButton('asmr-player-rewind-track', 'replay_5', 'Back 5 seconds', 'asmr-player-control-btn', function () {
      seekBy(-5)
    })
    var forward = createIconButton('asmr-player-forward-track', 'forward_30', 'Forward 30 seconds', 'asmr-player-control-btn', function () {
      seekBy(30)
    })
    var next = createIconButton('asmr-player-next-track', 'skip_next', 'Next track', 'asmr-player-control-btn', function () {
      commitAudioPlayer('NEXT_TRACK')
    })
    prev.style.order = '1'
    rewind.style.order = '2'
    forward.style.order = '4'
    next.style.order = '5'
    ;[prev, rewind, forward, next].forEach(function (btn) {
      if (btn.parentElement !== row) row.appendChild(btn)
    })

    var utility = document.getElementById('asmr-player-utility-row')
    if (!utility) {
      utility = document.createElement('div')
      utility.id = 'asmr-player-utility-row'
      utility.className = 'asmr-player-utility-row'
      var volumeRow = document.querySelector('.audio-player > .row.items-center.q-mx-lg')
      if (volumeRow && volumeRow.parentElement) {
        volumeRow.parentElement.insertBefore(utility, volumeRow.nextSibling)
      } else {
        row.parentElement.insertBefore(utility, row.nextSibling)
      }
    }

    var queue = createIconButton('asmr-player-queue-proxy', 'queue_music', 'Current playlist', 'asmr-player-utility-btn', function () {
      clickNode(roles.queue)
    })
    var modeIcon = (roles.mode && (roles.mode.innerText || roles.mode.textContent || '').trim()) || 'playlist_play'
    var mode = createIconButton('asmr-player-mode-proxy', modeIcon, 'Play mode', 'asmr-player-utility-btn', function () {
      clickNode(roles.mode)
    })
    var detail = document.getElementById('asmr-player-detail-proxy')
    if (detail) detail.remove()
    var subtitles = document.getElementById('asmr-lyrics-preview-toggle')
    if (!subtitles) {
      subtitles = document.createElement('button')
      subtitles.id = 'asmr-lyrics-preview-toggle'
      subtitles.type = 'button'
      subtitles.addEventListener('click', function (event) {
        event.preventDefault()
        event.stopPropagation()
        loadLyricsForCurrentTrack()
        togglePanel()
      })
    }
    if (subtitles.className !== 'asmr-lyrics-preview-toggle') subtitles.className = 'asmr-lyrics-preview-toggle'
    if (subtitles.title !== 'Lyrics preview') subtitles.title = 'Lyrics preview'
    if (subtitles.getAttribute('aria-label') !== 'Open lyrics preview') {
      subtitles.setAttribute('aria-label', 'Open lyrics preview')
    }
    var icon = subtitles.firstElementChild
    if (!icon || icon.tagName !== 'SPAN') {
      subtitles.textContent = ''
      icon = document.createElement('span')
      subtitles.appendChild(icon)
    }
    if (icon.className !== 'asmr-lyrics-preview-toggle__icon') icon.className = 'asmr-lyrics-preview-toggle__icon'
    if (icon.textContent !== 'subtitles') icon.textContent = 'subtitles'
    updateTogglePressed()

    var more = createIconButton('asmr-player-more-proxy', 'more_horiz', 'More', 'asmr-player-utility-btn', function () {
      clickNode(document.querySelector('.audio-player .albumart .absolute-top-right'))
      setTimeout(syncMoreMenu, 0)
      setTimeout(syncMoreMenu, 80)
    })
    ;[queue, mode, subtitles, more].forEach(function (btn) {
      if (btn.parentElement !== utility) utility.appendChild(btn)
    })

    row.querySelectorAll('.asmr-lyrics-preview-toggle').forEach(function (btn) {
      if (btn.parentElement !== utility) btn.remove()
    })
  }

  function bindAudioEvents () {
    var audio = getAudio()
    if (!audio || audio.dataset.asmrLyricsPanelBound) return
    audio.dataset.asmrLyricsPanelBound = '1'
    ;['timeupdate', 'seeked', 'loadeddata', 'play', 'pause'].forEach(function (eventName) {
      audio.addEventListener(eventName, function () {
        updateActiveLine(false)
      })
    })
  }

  function tick () {
    syncToggleButton()
    syncMoreMenu()
    bindAudioEvents()
    loadLyricsForCurrentTrack()
    updateActiveLine(false)
  }

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && state.open) closePanel()
  }, true)

  window.AsmrLyricsPanel = {
    open: openPanel,
    close: closePanel,
    reload: function () {
      state.hash = ''
      loadLyricsForCurrentTrack()
    },
    getState: function () {
      return {
        hash: state.hash,
        workId: state.workId,
        subtitleHash: state.subtitleHash,
        lines: state.lines.length,
        activeIndex: state.activeIndex,
        offset: state.offset
      }
    },
    _parseLrc: parseLrc
  }

  setInterval(tick, 1500)
  tick()
}())
