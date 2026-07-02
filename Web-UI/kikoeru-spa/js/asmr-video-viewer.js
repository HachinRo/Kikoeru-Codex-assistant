(function () {
  var active = null

  function ensureStyles () {
    if (document.getElementById('asmr-video-viewer-style')) return
    var style = document.createElement('style')
    style.id = 'asmr-video-viewer-style'
    style.textContent = [
      '.asmr-video-viewer{position:fixed;inset:0;z-index:100020;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;padding:20px;font-family:Roboto,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}',
      '.asmr-video-viewer__panel{width:min(1120px,100%);max-height:calc(100vh - 40px);background:#111;color:#fff;border-radius:6px;box-shadow:0 16px 46px rgba(0,0,0,.55);display:flex;flex-direction:column;overflow:hidden;}',
      '.asmr-video-viewer__bar{min-height:48px;display:flex;align-items:center;gap:10px;padding:8px 10px 8px 14px;background:#1d1d1d;border-bottom:1px solid rgba(255,255,255,.12);}',
      '.asmr-video-viewer__title{flex:1;min-width:0;font-size:14px;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
      '.asmr-video-viewer__button{height:32px;min-width:32px;border:0;border-radius:4px;background:rgba(255,255,255,.12);color:#fff;font:inherit;cursor:pointer;padding:0 10px;}',
      '.asmr-video-viewer__button:hover{background:rgba(255,255,255,.2);}',
      '.asmr-video-viewer__button--icon{font-size:22px;line-height:30px;padding:0;}',
      '.asmr-video-viewer__stage{background:#000;display:flex;align-items:center;justify-content:center;}',
      '.asmr-video-viewer video{display:block;width:100%;max-height:calc(100vh - 110px);background:#000;outline:0;}',
      '@media (max-width:640px){.asmr-video-viewer{padding:0;align-items:stretch;}.asmr-video-viewer__panel{width:100%;max-height:100vh;border-radius:0;}.asmr-video-viewer__title{font-size:13px;}.asmr-video-viewer video{max-height:calc(100vh - 52px);}}'
    ].join('')
    document.head.appendChild(style)
  }

  function tokenUrl (url) {
    return String(url || '')
  }

  function close () {
    if (!active) return
    var video = active.querySelector('video')
    if (video) {
      if (typeof video.pause === 'function') video.pause()
      video.removeAttribute('src')
      if (typeof video.load === 'function') video.load()
    }
    active.remove()
    active = null
    document.removeEventListener('keydown', onKeyDown, true)
  }

  function onKeyDown (event) {
    if (event.key === 'Escape') close()
  }

  function openExternal (url) {
    if (!url) return
    var link = document.createElement('a')
    link.href = url
    link.target = '_blank'
    link.rel = 'noopener'
    link.click()
  }

  function open (detail) {
    detail = detail || {}
    var url = tokenUrl(detail.url)
    if (!url) return

    close()
    ensureStyles()

    var overlay = document.createElement('div')
    overlay.className = 'asmr-video-viewer'
    overlay.setAttribute('role', 'dialog')
    overlay.setAttribute('aria-modal', 'true')
    overlay.addEventListener('click', function (event) {
      if (event.target === overlay) close()
    })

    var panel = document.createElement('div')
    panel.className = 'asmr-video-viewer__panel'
    panel.addEventListener('click', function (event) {
      event.stopPropagation()
    })

    var bar = document.createElement('div')
    bar.className = 'asmr-video-viewer__bar'

    var title = document.createElement('div')
    title.className = 'asmr-video-viewer__title'
    title.textContent = detail.title || 'Video'

    var openButton = document.createElement('button')
    openButton.className = 'asmr-video-viewer__button'
    openButton.type = 'button'
    openButton.textContent = 'Open'
    openButton.addEventListener('click', function () { openExternal(url) })

    var downloadButton = document.createElement('button')
    downloadButton.className = 'asmr-video-viewer__button'
    downloadButton.type = 'button'
    downloadButton.textContent = 'Download'
    downloadButton.addEventListener('click', function () {
      openExternal(detail.downloadUrl || url)
    })

    var closeButton = document.createElement('button')
    closeButton.className = 'asmr-video-viewer__button asmr-video-viewer__button--icon'
    closeButton.type = 'button'
    closeButton.setAttribute('aria-label', 'Close video viewer')
    closeButton.textContent = 'x'
    closeButton.addEventListener('click', close)

    var stage = document.createElement('div')
    stage.className = 'asmr-video-viewer__stage'

    var video = document.createElement('video')
    video.controls = true
    video.autoplay = true
    video.playsInline = true
    video.preload = 'metadata'
    video.src = url

    stage.appendChild(video)
    bar.appendChild(title)
    bar.appendChild(openButton)
    bar.appendChild(downloadButton)
    bar.appendChild(closeButton)
    panel.appendChild(bar)
    panel.appendChild(stage)
    overlay.appendChild(panel)
    document.body.appendChild(overlay)
    active = overlay
    document.addEventListener('keydown', onKeyDown, true)
    if (typeof video.focus === 'function') video.focus()
  }

  window.AsmrVideoViewer = { open: open, close: close }
  window.addEventListener('asmr:open-video', function (event) {
    open(event.detail)
  })
}())
