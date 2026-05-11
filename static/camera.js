let activeSourceType = 'webcam'

function updateDeviceStatus(message) {
  document.getElementById('device-status').textContent = message
}

function setSourceTabs(sourceType) {
  activeSourceType = sourceType
  document.querySelectorAll('.source-tab').forEach((button) => {
    const isActive = button.dataset.sourceType === sourceType
    button.classList.toggle('active', isActive)
    button.classList.toggle('secondary', !isActive)
  })
  document.getElementById('webcam-pane').classList.toggle('hidden', sourceType !== 'webcam')
  document.getElementById('rtsp-pane').classList.toggle('hidden', sourceType !== 'rtsp')
}

function renderWebcamOptions(webcams, selectedValue) {
  const select = document.getElementById('webcam-select')
  select.innerHTML = ''
  if (!webcams.length) {
    const option = document.createElement('option')
    option.value = '0'
    option.textContent = 'Khong tim thay webcam'
    select.appendChild(option)
    updateDeviceStatus('Khong tim thay webcam nao')
    return
  }

  webcams.forEach((webcam) => {
    const option = document.createElement('option')
    option.value = webcam.id
    option.textContent = webcam.label
    option.selected = webcam.id === selectedValue
    select.appendChild(option)
  })
  updateDeviceStatus(`Da tim thay ${webcams.length} webcam`)
}

async function loadCameraDevices() {
  updateDeviceStatus('Dang do webcam...')
  const response = await fetch('/api/camera/devices')
  const data = await response.json()
  renderWebcamOptions(data.devices || [], data.selected_source_value)
}

function renderState(data) {
  document.getElementById('people-count').textContent = data.people_count
  document.getElementById('group-count').textContent = data.pending_group_count
  document.getElementById('camera-state').textContent = data.camera_ready ? 'Running' : 'Idle'
  document.getElementById('camera-source').textContent = data.camera_label
  document.getElementById('camera-connected').textContent = data.camera_connected ? 'Da ket noi' : 'Chua ket noi'
  document.getElementById('camera-success').textContent = data.camera_ready ? 'Thanh cong' : 'Chua bat'
  document.getElementById('status-line').textContent = data.status_line
  document.getElementById('rtsp-input').value = data.camera_source_type === 'rtsp' ? data.camera_source_value : ''
  setSourceTabs(data.camera_source_type)

  const video = document.getElementById('video-feed')
  if (data.camera_enabled) {
    if (video.dataset.src !== data.video_feed_url) {
      video.src = data.video_feed_url
      video.dataset.src = data.video_feed_url
    }
  } else if (video.getAttribute('src')) {
    video.removeAttribute('src')
    video.dataset.src = ''
  }
}

async function loadState() {
  const response = await fetch('/api/state')
  const data = await response.json()
  renderState(data)
}

async function postJson(url, payload = undefined) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined,
  })
  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Request failed')
  }
  const data = await response.json()
  renderState(data)
}

async function runAction(action) {
  try {
    await action()
  } catch (error) {
    document.getElementById('status-line').textContent = error.message
  }
}

document.querySelectorAll('.source-tab').forEach((button) => {
  button.addEventListener('click', () => setSourceTabs(button.dataset.sourceType))
})

document.getElementById('scan-devices').addEventListener('click', async () => {
  await runAction(loadCameraDevices)
})

document.getElementById('save-webcam').addEventListener('click', async () => {
  await runAction(() => postJson('/api/camera/configure', {
    source_type: 'webcam',
    source_value: document.getElementById('webcam-select').value,
  }))
})

document.getElementById('save-rtsp').addEventListener('click', async () => {
  await runAction(() => postJson('/api/camera/configure', {
    source_type: 'rtsp',
    source_value: document.getElementById('rtsp-input').value,
  }))
})

document.getElementById('start-camera').addEventListener('click', async () => {
  await runAction(() => postJson('/api/camera/start'))
})

document.getElementById('stop-camera').addEventListener('click', async () => {
  await runAction(() => postJson('/api/camera/stop'))
})

loadState()
updateDeviceStatus('Nhan Do webcam de tim thiet bi tren may.')
setInterval(loadState, 4000)
