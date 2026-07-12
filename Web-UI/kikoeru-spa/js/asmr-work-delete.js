(function () {
  var buttonId = 'asmr-work-delete'
  var refreshButtonId = 'asmr-work-refresh'
  var modalId = 'asmr-work-delete-modal'
  var currentPath = ''

  function workPathId () {
    var match = window.location.pathname.match(/^\/work\/([^/]+)\/?$/)
    return match ? decodeURIComponent(match[1]) : ''
  }

  function removeNode (id) {
    var node = document.getElementById(id)
    if (node && node.parentNode) node.parentNode.removeChild(node)
  }

  function jsonFetch (url, options) {
    return fetch(url, options).then(function (res) {
      return res.json().then(function (json) {
        if (!res.ok) throw new Error(json.error || res.status + ' ' + res.statusText)
        return json
      })
    })
  }

  function dashboardAuthHeader () {
    try {
      return window.sessionStorage.getItem('asmrAdminBasicAuth') || ''
    } catch (err) {
      return ''
    }
  }

  function waitAction (id) {
    return new Promise(function (resolve, reject) {
      function poll () {
        jsonFetch('/api/asmr-library/actions/' + encodeURIComponent(id))
          .then(function (action) {
            if (action.status === 'running') return window.setTimeout(poll, 1200)
            if (action.status === 'done') return resolve(action)
            reject(new Error(action.error || action.output || 'Action failed'))
          })
          .catch(reject)
      }
      poll()
    })
  }

  function refreshWork (workId, btn) {
    var auth = dashboardAuthHeader()
    if (!auth) {
      window.alert('请先在管理面板保存管理员登录信息，然后再刷新作品。')
      window.location.href = '/asmr-library'
      return
    }
    btn.disabled = true
    btn.setAttribute('aria-busy', 'true')
    jsonFetch('/api/asmr-library/actions/fix-content', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': auth,
        'X-ASMR-Dashboard-Request': '1'
      },
      body: JSON.stringify({ rj: workId })
    }).then(function (action) {
      return waitAction(action.id)
    }).then(function () {
      return jsonFetch('/api/admin/refresh-cache', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': auth,
          'X-ASMR-Dashboard-Request': '1'
        },
        body: JSON.stringify({})
      })
    }).then(function () {
      window.location.reload()
    }).catch(function (err) {
      btn.disabled = false
      btn.removeAttribute('aria-busy')
      window.alert('刷新作品失败: ' + err.message)
    })
  }

  function showModal (workId, work) {
    removeNode(modalId)
    var rj = String(work.rj_id || work.id || '').toUpperCase()
    var title = work.title || work.name || rj

    var overlay = document.createElement('div')
    overlay.id = modalId
    overlay.className = 'asmr-delete-overlay'

    var dialog = document.createElement('div')
    dialog.className = 'asmr-delete-dialog'

    var heading = document.createElement('h2')
    heading.textContent = 'Permanently delete work'

    var text = document.createElement('p')
    text.textContent = 'This will delete ' + rj + ', its media folder, cover files, database rows, and then run a fresh reindex. This cannot be undone.'

    var titleLine = document.createElement('p')
    titleLine.className = 'asmr-delete-title'
    titleLine.textContent = title

    var input = document.createElement('input')
    input.type = 'text'
    input.autocomplete = 'off'
    input.spellcheck = false
    input.placeholder = 'Type ' + rj + ' to confirm'

    var actions = document.createElement('div')
    actions.className = 'asmr-delete-actions'

    var cancel = document.createElement('button')
    cancel.type = 'button'
    cancel.textContent = 'Cancel'
    cancel.className = 'asmr-delete-cancel'
    cancel.addEventListener('click', function () { removeNode(modalId) })

    var confirm = document.createElement('button')
    confirm.type = 'button'
    confirm.textContent = 'Delete forever'
    confirm.className = 'asmr-delete-confirm'
    confirm.disabled = true

    input.addEventListener('input', function () {
      confirm.disabled = input.value.trim().toUpperCase() !== rj
    })

    confirm.addEventListener('click', function () {
      var auth = dashboardAuthHeader()
      if (!auth) {
        window.alert('Log in to the ASMR library dashboard first, then return to this work and delete it.')
        window.location.href = '/asmr-library'
        return
      }
      confirm.disabled = true
      cancel.disabled = true
      input.disabled = true
      confirm.textContent = 'Deleting and reindexing...'
      jsonFetch('/api/work/' + encodeURIComponent(workId), {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'Authorization': auth },
        body: JSON.stringify({ confirmation: input.value.trim() })
      }).then(function () {
        removeNode(modalId)
        window.location.href = '/works'
      }).catch(function (err) {
        confirm.disabled = false
        cancel.disabled = false
        input.disabled = false
        confirm.textContent = 'Delete forever'
        if (/admin credentials/i.test(err.message)) {
          window.alert('Log in to the ASMR library dashboard first, then return to this work and delete it.')
          window.location.href = '/asmr-library'
        } else {
          window.alert('Delete failed: ' + err.message)
        }
      })
    })

    actions.appendChild(cancel)
    actions.appendChild(confirm)
    dialog.appendChild(heading)
    dialog.appendChild(text)
    dialog.appendChild(titleLine)
    dialog.appendChild(input)
    dialog.appendChild(actions)
    overlay.appendChild(dialog)
    document.body.appendChild(overlay)
    input.focus()
  }

  function ensureButton () {
    var workId = workPathId()
    if (!workId) {
      removeNode(buttonId)
      removeNode(refreshButtonId)
      removeNode(modalId)
      currentPath = ''
      return
    }
    if (currentPath === window.location.pathname && document.getElementById(buttonId) && document.getElementById(refreshButtonId)) return
    currentPath = window.location.pathname
    removeNode(buttonId)
    removeNode(refreshButtonId)

    var salesRow = Array.prototype.find.call(document.querySelectorAll('.q-pt-sm.q-pb-none'), function (node) {
      return /售出数\s*:/.test(node.textContent || '')
    })
    if (!salesRow) return

    var refreshBtn = document.createElement('button')
    refreshBtn.id = refreshButtonId
    refreshBtn.type = 'button'
    refreshBtn.title = '刷新作品'
    refreshBtn.setAttribute('aria-label', '刷新作品')
    refreshBtn.innerHTML = '<span class="material-icons">refresh</span>'
    refreshBtn.addEventListener('click', function () { refreshWork(workId, refreshBtn) })

    var btn = document.createElement('button')
    btn.id = buttonId
    btn.type = 'button'
    btn.title = '删除作品'
    btn.setAttribute('aria-label', '删除作品')
    btn.innerHTML = '<span class="material-icons">delete_forever</span>'
    btn.addEventListener('click', function () {
      btn.disabled = true
      jsonFetch('/api/work/' + encodeURIComponent(workId))
        .then(function (work) { showModal(workId, work) })
        .catch(function (err) { window.alert('Could not load work: ' + err.message) })
        .finally(function () { btn.disabled = false })
    })
    salesRow.appendChild(refreshBtn)
    salesRow.appendChild(btn)
  }

  function patchHistory (name) {
    var original = window.history[name]
    window.history[name] = function () {
      var result = original.apply(this, arguments)
      window.setTimeout(ensureButton, 50)
      return result
    }
  }

  patchHistory('pushState')
  patchHistory('replaceState')
  window.addEventListener('popstate', function () { window.setTimeout(ensureButton, 50) })
  window.setInterval(ensureButton, 1000)
  ensureButton()
}())
