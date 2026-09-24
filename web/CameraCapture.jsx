import React, { useEffect, useRef, useState } from 'react';
import { Camera, SwitchCamera, X, Check, RotateCcw, Smartphone } from 'lucide-react';
import './camera.css';

export default function CameraCapture({ busy, onAnalyze }) {
  const video = useRef(null),
    stream = useRef(null),
    generation = useRef(0),
    nativeInput = useRef(null);
  const [opening, setOpening] = useState(false),
    [active, setActive] = useState(false);
  const [ready, setReady] = useState(false),
    [facing, setFacing] = useState('user');
  const [shot, setShot] = useState(null),
    [error, setError] = useState('');

  function stopTracks() {
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
  }

  function close() {
    generation.current++;
    stopTracks();
    setActive(false);
    setReady(false);
    setOpening(false);
  }

  useEffect(() => () => {
    generation.current++;
    stopTracks();
  }, []);

  useEffect(() => {
    const hide = () => {
      if (document.hidden) close();
    };
    document.addEventListener('visibilitychange', hide);
    return () => document.removeEventListener('visibilitychange', hide);
  }, []);

  useEffect(() => {
    if (!shot) return;
    return () => URL.revokeObjectURL(shot.url);
  }, [shot]);

  async function openCamera(direction = facing) {
    close();
    setError('');
    setShot(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Trình duyệt chưa hỗ trợ camera trực tiếp. Hãy dùng nút chụp ảnh.');
      return;
    }
    const request = ++generation.current;
    setOpening(true);
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: direction }, width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      if (request !== generation.current) {
        media.getTracks().forEach(t => t.stop());
        return;
      }
      stream.current = media;
      setFacing(direction);
      setActive(true);
      setOpening(false);
      video.current.srcObject = media;
      await video.current.play();
    } catch (err) {
      if (request !== generation.current) return;
      close();
      setError('Không thể mở camera. Vui lòng cấp quyền hoặc tải ảnh trực tiếp.');
    }
  }

  function capture() {
    const v = video.current;
    if (!v?.videoWidth || !ready) return;
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext('2d').drawImage(v, 0, 0);
    const request = generation.current;
    canvas.toBlob(blob => {
      if (!blob || request !== generation.current) return;
      setShot({ file: new File([blob], 'camera.jpg', { type: 'image/jpeg' }), url: URL.createObjectURL(blob) });
      close();
    }, 'image/jpeg', 0.92);
  }

  function nativePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    close();
    setError('');
    setShot({ file, url: URL.createObjectURL(file) });
  }

  return (
    <section className="card camera-card" style={{ padding: '16px 20px', marginBottom: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Camera size={20} color="#0f766e" />
          <h2 style={{ margin: 0, fontSize: '15px' }}>Chụp & Quét khuôn mặt</h2>
        </div>

        <div className="camera-actions" style={{ margin: 0, gap: '8px' }}>
          <button className="primary" disabled={busy || opening} onClick={() => openCamera()}>
            <Camera size={16} />
            {opening ? 'Đang mở…' : 'Mở Camera'}
          </button>
          <button disabled={busy} onClick={() => nativeInput.current.click()}>
            <Smartphone size={16} />
            Chụp điện thoại
          </button>
          <input ref={nativeInput} type="file" accept="image/*" capture="environment" hidden onChange={nativePhoto} />
          {(active || opening) && (
            <button onClick={close}>
              <X size={16} />
              Đóng
            </button>
          )}
        </div>
      </div>

      {error && <p role="alert" className="camera-error" style={{ margin: '10px 0 0', fontSize: '12px' }}>{error}</p>}

      <video
        ref={video}
        hidden={!active}
        autoPlay
        muted
        playsInline
        onLoadedData={() => setReady(true)}
        className="camera-preview"
        style={{ marginTop: '12px', maxHeight: '360px', width: '100%', objectFit: 'cover', borderRadius: '10px' }}
      />

      {active && (
        <div className="camera-actions" style={{ marginTop: '10px' }}>
          <button className="primary" disabled={!ready || busy} onClick={capture}>
            <Camera size={16} />
            Chụp ảnh này
          </button>
          <button disabled={opening || busy} onClick={() => openCamera(facing === 'user' ? 'environment' : 'user')}>
            <SwitchCamera size={16} />
            Đổi góc camera
          </button>
        </div>
      )}

      {shot && (
        <div style={{ marginTop: '12px' }}>
          <img
            className="camera-preview"
            src={shot.url}
            alt="Ảnh chụp"
            style={{ maxHeight: '280px', width: '100%', objectFit: 'contain', borderRadius: '10px', background: '#000' }}
          />
          <div className="camera-actions" style={{ marginTop: '10px' }}>
            <button
              className="primary"
              disabled={busy}
              onClick={() => {
                onAnalyze(shot.file);
                setShot(null);
              }}
            >
              <Check size={16} />
              Quét khuôn mặt này
            </button>
            <button disabled={busy} onClick={() => openCamera()}>
              <RotateCcw size={16} />
              Chụp lại
            </button>
            <button disabled={busy} onClick={() => setShot(null)}>
              <X size={16} />
              Hủy
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
