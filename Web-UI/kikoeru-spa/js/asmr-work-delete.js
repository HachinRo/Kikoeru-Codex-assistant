(function () {
  var buttonId = 'asmr-work-delete'
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
      removeNode(modalId)
      currentPath = ''
      return
    }
    if (currentPath === window.location.pathname && document.getElementById(buttonId)) return
    currentPath = window.location.pathname
    removeNode(buttonId)

    var btn = document.createElement('button')
    btn.id = buttonId
    btn.type = 'button'
    btn.title = 'Delete this work permanently'
    btn.setAttribute('aria-label', 'Delete this work permanently')
    btn.innerHTML = '<span class="material-icons">delete_forever</span>'
    btn.addEventListener('click', function () {
      btn.disabled = true
      jsonFetch('/api/work/' + encodeURIComponent(workId))
        .then(function (work) { showModal(workId, work) })
        .catch(function (err) { window.alert('Could not load work: ' + err.message) })
        .finally(function () { btn.disabled = false })
    })
    document.body.appendChild(btn)
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
