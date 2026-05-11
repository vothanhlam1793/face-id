function personOptions(people, selectedId = '') {
  const items = ['<option value="">Chon nguoi da co</option>']
  for (const person of people) {
    const selected = person.id === selectedId ? 'selected' : ''
    items.push(`<option value="${person.id}" ${selected}>${person.name}</option>`)
  }
  return items.join('')
}

async function postForm(url, payload) {
  const body = new URLSearchParams()
  for (const [key, value] of Object.entries(payload)) body.set(key, value)
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(data.detail || 'Request failed')
  }
  return response.json()
}

async function createPerson(groupId, form) {
  const name = form.querySelector('input').value.trim()
  if (!name) return
  try {
    await postForm('/api/groups/create_person', { group_id: groupId, name })
    await loadReview()
  } catch (error) {
    alert(error.message)
  }
}

async function attachPerson(groupId, form) {
  const personId = form.querySelector('select').value
  if (!personId) return
  try {
    await postForm('/api/groups/attach_person', { group_id: groupId, person_id: personId })
    await loadReview()
  } catch (error) {
    alert(error.message)
  }
}

async function acceptSuggestion(groupId, personId) {
  try {
    await postForm('/api/groups/attach_person', { group_id: groupId, person_id: personId })
    await loadReview()
  } catch (error) {
    alert(error.message)
  }
}

async function dismissGroup(groupId) {
  try {
    await postForm('/api/groups/dismiss', { group_id: groupId })
    await loadReview()
  } catch (error) {
    alert(error.message)
  }
}

async function deleteSample(groupId, sampleId) {
  try {
    await postForm('/api/groups/delete_sample', { group_id: groupId, sample_id: sampleId })
    await loadReview()
  } catch (error) {
    alert(error.message)
  }
}

async function recheckGroups() {
  try {
    const result = await postForm('/api/groups/recheck', {})
    await loadReview()
    alert(`Da quet lai ${result.scanned} groups, co ${result.suggested} goi y, auto-merge ${result.merged_groups || 0} groups.`)
  } catch (error) {
    alert(error.message)
  }
}

async function rebuildEmbeddings() {
  try {
    const result = await postForm('/api/system/rebuild_embeddings', {})
    await loadReview()
    alert(`Da rebuild ${result.rebuilt_people} nguoi voi ${result.rebuilt_samples} anh mau.`)
  } catch (error) {
    alert(error.message)
  }
}

async function importImages(form) {
  const input = form.querySelector('#image-files')
  if (!input.files.length) return

  const body = new FormData()
  for (const file of input.files) {
    body.append('files', file)
  }

  try {
    const response = await fetch('/api/groups/import_images', {
      method: 'POST',
      body,
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({ detail: 'Import failed' }))
      throw new Error(data.detail || 'Import failed')
    }

    const result = await response.json()
    input.value = ''
    await loadReview()
    alert(`Da import ${result.imported_files} file, quet ${result.scanned_frames || 0} frame video, tach duoc ${result.detected_faces} khuon mat, tao ${result.created_groups} groups, auto-merge ${result.merged_groups || 0} groups.`)
  } catch (error) {
    alert(error.message)
  }
}

function renderGroups(groups, people) {
  const target = document.getElementById('group-list')
  if (!groups.length) {
    target.innerHTML = '<div class="empty">Khong con unknown group nao cho xu ly.</div>'
    return
  }

  target.innerHTML = groups.map(group => `
    <div class="card">
      <strong>${group.label}</strong>
      <div class="meta">Bat dau: ${group.created_at} | So mau: ${group.sample_count}</div>
      ${group.suggested_person_name ? `<div class="badge">Goi y: ${group.suggested_person_name} (${group.suggested_score.toFixed(2)})</div>` : ''}
      <div class="thumbs">${group.samples.map(sample => `<div class="thumb"><img src="${sample.snapshot_url}" alt="sample" /><button class="secondary" onclick="deleteSample('${group.id}', '${sample.id}')">Xoa anh</button></div>`).join('')}</div>
      <div class="stack">
        <form onsubmit="event.preventDefault(); createPerson('${group.id}', this)">
          <div class="row"><input placeholder="Nhap ten nguoi moi" /><button type="submit">Tao moi</button></div>
        </form>
        <form onsubmit="event.preventDefault(); attachPerson('${group.id}', this)">
          <div class="row"><select>${personOptions(people, group.suggested_person_id || '')}</select><button type="submit">Gan nguoi cu</button></div>
        </form>
        <div class="row">
          ${group.suggested_person_id ? `<button class="secondary" onclick="acceptSuggestion('${group.id}', '${group.suggested_person_id}')">Nhan goi y</button>` : ''}
          <button class="secondary" onclick="dismissGroup('${group.id}')">Bo qua</button>
        </div>
      </div>
    </div>
  `).join('')
}

async function loadReview() {
  const response = await fetch('/api/review_state')
  const data = await response.json()
  renderGroups(data.groups, data.people)
}

loadReview()
