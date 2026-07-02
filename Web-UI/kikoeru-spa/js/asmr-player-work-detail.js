(function () {
  var workDetailLabel = '打开作品详情'

  function compactText (value) {
    return String(value || '').replace(/\s+/g, '')
  }

  function isWorkDetailMenuClick (target) {
    var node = target && (target.nodeType === 1 ? target : target.parentElement)
    while (node && node !== document.body) {
      if (compactText(node.textContent) === workDetailLabel) return true
      if (node.classList && node.classList.contains('q-menu')) return false
      node = node.parentElement
    }
    return false
  }

  function normalizeWorkId (value) {
    var raw = String(value || '').trim()
    if (!raw) return ''
    var first = raw.split('/')[0]
    if (/^RJ\d+$/i.test(first)) return first.toUpperCase()
    if (/^\d+$/.test(first)) return first
    return ''
  }

  function getAppVm () {
    var root = document.getElementById('q-app')
    return root && root.__vue__
  }

  function getCurrentPlayingFile () {
    var vm = getAppVm()
    var store = vm && vm.$store
    if (!store || !store.getters) return null
    return store.getters['AudioPlayer/currentPlayingFile'] || null
  }

  function workIdFromTrack (track) {
    if (!track) return ''
    return normalizeWorkId(track.rj_id) ||
      normalizeWorkId(track.rjId) ||
      normalizeWorkId(track.work_id) ||
      normalizeWorkId(track.workId) ||
      normalizeWorkId(track.hash)
  }

  function currentHashFromAudio () {
    var source = document.querySelector('audio source[src*="/api/media/stream/"]')
    var audio = document.querySelector('audio[src*="/api/media/stream/"]')
    var src = source ? source.getAttribute('src') : (audio && audio.getAttribute('src'))
    var match = src && src.match(/\/api\/media\/stream\/([^/?#]+)/)
    return match ? decodeURIComponent(match[1]) : ''
  }

  function currentHash () {
    var current = getCurrentPlayingFile()
    return (current && current.hash) || currentHashFromAudio()
  }

  function navigateToWork (workId) {
    var normalized = normalizeWorkId(workId)
    if (!normalized) return false
    if (/^\d+$/.test(normalized)) {
      fetch('/api/work/' + encodeURIComponent(normalized))
        .then(function (res) {
          if (!res.ok) throw new Error(res.status + ' ' + res.statusText)
          return res.json()
        })
        .then(function (work) {
          var canonical = normalizeWorkId(work && (work.id || work.rj_id || work.rjId))
          if (canonical && canonical !== normalized) {
            navigateToWork(canonical)
          } else {
            console.warn('Could not open work details: unresolved numeric work id', normalized, work)
          }
        })
        .catch(function (err) {
          console.warn('Could not open work details:', err)
        })
      return true
    }
    var target = '/work/' + encodeURIComponent(normalized)
    if (window.location.pathname === target) return true

    var vm = getAppVm()
    var router = vm && vm.$router
    if (router && typeof router.push === 'function') {
      var pushed = router.push(target)
      if (pushed && typeof pushed.catch === 'function') pushed.catch(function () {})
      return true
    }

    window.location.assign(target)
    return true
  }

  function openCurrentWorkDetail () {
    var current = getCurrentPlayingFile()
    var directWorkId = workIdFromTrack(current)
    if (navigateToWork(directWorkId)) return

    var hash = currentHash()
    if (!hash) {
      console.warn('Could not open work details: no current media hash')
      return
    }

    fetch('/api/track/' + encodeURIComponent(hash))
      .then(function (res) {
        if (!res.ok) throw new Error(res.status + ' ' + res.statusText)
        return res.json()
      })
      .then(function (track) {
        if (!navigateToWork(workIdFromTrack(track))) {
          console.warn('Could not open work details: track has no work id', track)
        }
      })
      .catch(function (err) {
        console.warn('Could not open work details:', err)
      })
  }

  document.addEventListener('click', function (event) {
    if (!isWorkDetailMenuClick(event.target)) return
    event.preventDefault()
    event.stopPropagation()
    event.stopImmediatePropagation()
    openCurrentWorkDetail()
  }, true)
}())
