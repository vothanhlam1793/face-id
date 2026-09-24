import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Users,
  ScanFace,
  Code,
  Plus,
  Search,
  Menu,
  Upload,
  ChevronLeft,
  ChevronRight,
  Save,
  LogOut,
  KeyRound,
  ShieldCheck,
  UserCheck,
  Lock,
  X,
  Sparkles,
  Zap,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import './style.css';
import CameraCapture from './CameraCapture.jsx';
import CaseHistory from './CaseHistory.jsx';

async function api(url, options = {}) {
  const r = await fetch('/api/v1/' + url, {
    ...options,
    headers: {
      'Accept': 'application/json',
      ...(options.headers || {})
    }
  });
  const data = await r.json().catch(() => ({ detail: 'Lỗi phản hồi máy chủ' }));
  if (!r.ok) {
    const msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return data;
}

function LoginView({ onLoggedIn, setToast }) {
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    if (!password) {
      setError('Vui lòng nhập mật khẩu');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const res = await api('auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password })
      });
      onLoggedIn(res.user);
      setToast('Đăng nhập thành công');
    } catch (err) {
      setError(err.message || 'Đăng nhập không thành công');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-box">
        <div className="login-header">
          <div className="login-logo">
            <ScanFace size={28} />
          </div>
          <h1>NOVA FACE</h1>
        </div>

        {error && <div className="login-alert">{error}</div>}

        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            Tài khoản
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
            />
          </label>

          <label>
            Mật khẩu
            <input
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              autoFocus
            />
          </label>

          <button type="submit" className="login-btn" disabled={busy}>
            <Lock size={15} />
            {busy ? 'Đang xác thực…' : 'Đăng nhập'}
          </button>
        </form>
      </div>
    </div>
  );
}

function App() {
  const [auth, setAuth] = useState({ loading: true, authenticated: false, user: null });
  const [tab, setTab] = useState('quality'); // Default landing is Face Check
  const [collapsed, collapse] = useState(false);
  const [health, setHealth] = useState(null);
  const [query, setQuery] = useState('');
  const [filterChip, setFilterChip] = useState('all');
  const [page, setPage] = useState(0);
  const [list, setList] = useState({ items: [], total: 0 });
  const [toast, setToast] = useState('');
  const [editing, setEditing] = useState(null);
  const [changingPassword, setChangingPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [preview, setPreview] = useState('');

  const dialog = useRef();
  const pwdDialog = useRef();
  const canvas = useRef();
  const searchInputRef = useRef();

  const isAdmin = auth.user?.role === 'admin';

  useEffect(() => {
    api('auth/me')
      .then(res => {
        if (res.authenticated) {
          setAuth({ loading: false, authenticated: true, user: res.user });
        } else {
          setAuth({ loading: false, authenticated: false, user: null });
        }
      })
      .catch(() => setAuth({ loading: false, authenticated: false, user: null }));
  }, []);

  const refresh = () => {
    if (!auth.authenticated) return;
    api('health').then(setHealth).catch(e => {
      if (e.status === 401) setAuth({ loading: false, authenticated: false, user: null });
      else setToast(e.message);
    });
  };

  useEffect(() => {
    if (auth.authenticated) refresh();
  }, [auth.authenticated]);

  useEffect(() => {
    if (auth.authenticated && !isAdmin && tab === 'people') {
      setTab('quality');
    }
  }, [auth.authenticated, isAdmin, tab]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(''), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  // Load personnel list (Admin only)
  useEffect(() => {
    if (!auth.authenticated || !isAdmin || tab !== 'people') return;
    const controller = new AbortController();

    let finalQuery = query.trim();
    if (filterChip === 'tech') finalQuery += ' Công nghệ';
    else if (filterChip === 'office') finalQuery += ' Văn phòng';

    const t = setTimeout(
      () =>
        api(`persons?q=${encodeURIComponent(finalQuery)}&offset=${page * 24}`, { signal: controller.signal })
          .then(setList)
          .catch(e => {
            if (e.name !== 'AbortError') {
              if (e.status === 401) setAuth({ loading: false, authenticated: false, user: null });
              else if (e.status === 403) setToast('Không có quyền xem danh bạ');
              else setToast(e.message);
            }
          }),
      180
    );
    return () => {
      clearTimeout(t);
      controller.abort();
    };
  }, [query, filterChip, page, editing, auth.authenticated, isAdmin, tab]);

  useEffect(() => {
    if (editing) dialog.current?.showModal();
    else dialog.current?.close();
  }, [editing]);

  useEffect(() => {
    if (changingPassword) pwdDialog.current?.showModal();
    else pwdDialog.current?.close();
  }, [changingPassword]);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  async function handleLogout() {
    try {
      await api('auth/logout', { method: 'POST' });
    } catch (_) {}
    setAuth({ loading: false, authenticated: false, user: null });
    setToast('Đã đăng xuất');
  }

  async function handleChangePassword(e) {
    e.preventDefault();
    const form = new FormData(e.target);
    const old_password = form.get('old_password');
    const new_password = form.get('new_password');
    const confirm_password = form.get('confirm_password');

    if (new_password !== confirm_password) {
      setToast('Mật khẩu xác nhận không khớp');
      return;
    }
    setBusy(true);
    try {
      await api('auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_password, new_password })
      });
      setChangingPassword(false);
      setToast('Đã đổi mật khẩu');
    } catch (err) {
      setToast(err.message || 'Lỗi đổi mật khẩu');
    } finally {
      setBusy(false);
    }
  }

  async function analyze(file) {
    if (!file || busy) return;
    setBusy(true);
    setResult(null);
    setPreview('');
    try {
      const form = new FormData();
      form.append('file', file);
      const data = await api('image-quality', { method: 'POST', body: form });
      setResult(data);
      setPreview(URL.createObjectURL(file));
    } catch (e) {
      if (e.status === 401) setAuth({ loading: false, authenticated: false, user: null });
      else setToast(e.message);
    } finally {
      setBusy(false);
    }
  }

  function draw(e) {
    const img = e.target,
      c = canvas.current;
    if (!c) return;
    c.width = img.naturalWidth;
    c.height = img.naturalHeight;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0);
    ctx.lineWidth = Math.max(3, c.width / 350);
    ctx.strokeStyle = '#0f766e';
    result?.faces.forEach(f => {
      ctx.strokeRect(...f.box);
      if (f.matched_person) {
        ctx.fillStyle = '#0f766e';
        const label = `${f.matched_person.name} (${f.matched_person.confidence}%)`;
        const fontSize = Math.max(12, Math.round(c.width / 35));
        ctx.font = `bold ${fontSize}px sans-serif`;
        const textWidth = ctx.measureText(label).width;
        ctx.fillRect(f.box[0], Math.max(0, f.box[1] - fontSize - 8), textWidth + 12, fontSize + 8);
        ctx.fillStyle = '#ffffff';
        ctx.fillText(label, f.box[0] + 6, Math.max(fontSize, f.box[1] - 4));
      }
    });
  }

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const values = Object.fromEntries(new FormData(e.target));
      await api('persons' + (editing.id ? '/' + editing.id : ''), {
        method: editing.id ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values)
      });
      setEditing(null);
      refresh();
      setToast('Đã lưu nhân sự');
    } catch (e) {
      if (e.status === 401) setAuth({ loading: false, authenticated: false, user: null });
      else setToast(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (auth.loading) {
    return (
      <div className="login-wrap">
        <div style={{ color: '#fff', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ScanFace size={20} /> Đang tải…
        </div>
      </div>
    );
  }

  if (!auth.authenticated) {
    return <LoginView onLoggedIn={user => setAuth({ loading: false, authenticated: true, user })} setToast={setToast} />;
  }

  const navItems = [
    ['quality', ScanFace, 'Quét mặt', true],
    ['people', Users, 'Danh bạ', isAdmin],
    ['api', Code, 'Hệ thống', true]
  ].filter(item => item[3]);

  return (
    <div className={'shell ' + (collapsed ? 'collapsed' : '')}>
      {/* Sidebar for Desktop */}
      <aside>
        <div className="brand">
          <ScanFace />
          <span>NOVA FACE</span>
        </div>

        {navItems.map(([id, Icon, label]) => (
          <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)} title={label}>
            <Icon />
            <span>{label}</span>
          </button>
        ))}

        <div className="aside-foot">
          <div className="user-badge">
            <div className="uname">
              <ShieldCheck size={15} />
              <span>{auth.user?.username}</span>
            </div>
            <div style={{ display: 'flex', gap: '2px' }}>
              <button title="Đổi mật khẩu" onClick={() => setChangingPassword(true)}>
                <KeyRound size={13} />
              </button>
              <button title="Đăng xuất" onClick={handleLogout}>
                <LogOut size={13} />
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main>
        {/* Compact Top Bar */}
        <div className="top-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {tab === 'quality' && <Zap size={20} color="#0f766e" />}
            {tab === 'people' && <Users size={20} color="#0f766e" />}
            {tab === 'api' && <Code size={20} color="#0f766e" />}
            <h1 style={{ margin: 0, fontSize: '18px' }}>
              {tab === 'quality' ? 'Quét & Nhận diện' : tab === 'people' ? 'Danh bạ nhân sự' : 'Thông tin hệ thống'}
            </h1>
          </div>

          <div className="badge-stat">
            <strong>{health?.persons_with_photo?.toLocaleString('vi-VN') ?? '2.491'}</strong>
            <span>vector mặt</span>
          </div>
        </div>

        {/* TAB 1: FACE QUALITY & RECOGNITION (DEFAULT) */}
        {tab === 'quality' && (
          <>
            <CameraCapture busy={busy} onAnalyze={analyze} />

            <div className="quality-grid">
              <section className="card" style={{ padding: '16px 20px' }}>
                <label
                  className="drop"
                  onDragOver={e => e.preventDefault()}
                  onDrop={e => {
                    e.preventDefault();
                    analyze(e.dataTransfer.files[0]);
                  }}
                >
                  <Upload size={28} />
                  <strong>{busy ? 'Đang nhận diện…' : 'Chọn hoặc kéo thả ảnh chân dung'}</strong>
                  <span>Hỗ trợ JPG / PNG</span>
                  <input type="file" accept="image/*" disabled={busy} onChange={e => analyze(e.target.files[0])} />
                </label>

                {preview && (
                  <div style={{ marginTop: '10px' }}>
                    <img src={preview} alt="" hidden onLoad={draw} />
                    <canvas ref={canvas} />
                  </div>
                )}
              </section>

              <section className="card" style={{ padding: '16px 20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h2 style={{ margin: 0, fontSize: '15px' }}>Kết quả nhận diện</h2>
                  {result && <code>{result.elapsed_ms} ms</code>}
                </div>

                {!result ? (
                  <div style={{ textAlign: 'center', padding: '30px 10px', color: '#94a3b8' }}>
                    <ScanFace size={36} style={{ margin: '0 auto 8px', opacity: 0.5 }} />
                    <p style={{ margin: 0, fontSize: '13px' }}>Chụp hoặc tải ảnh để xem kết quả</p>
                  </div>
                ) : (
                  <>
                    {!result.total_faces ? (
                      <div className="alert-box alert-error">
                        <AlertCircle size={16} />
                        <span>Không tìm thấy khuôn mặt trong ảnh</span>
                      </div>
                    ) : (
                      result.faces.map((f, i) => (
                        <div className="face-card" key={i}>
                          {/* Person Result Card */}
                          {f.matched_person ? (
                            <div className="person-match-row">
                              {f.matched_person.photo_url ? (
                                <img
                                  src={f.matched_person.photo_url}
                                  alt={f.matched_person.name}
                                  className="match-avatar"
                                />
                              ) : (
                                <div className="match-avatar avatar-placeholder">
                                  <Users size={20} />
                                </div>
                              )}
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                                  <span className="match-name">{f.matched_person.name}</span>
                                  <span className="badge-code">{f.matched_person.employee_id}</span>
                                  <span className="badge-confidence">{f.matched_person.confidence}% khớp</span>
                                </div>
                                <div className="match-sub">{f.matched_person.title}</div>
                                <div className="match-dept">{f.matched_person.department}</div>
                              </div>
                            </div>
                          ) : (
                            <div style={{ color: '#64748b', fontSize: '13px', margin: '4px 0 8px' }}>
                              Chưa nhận diện được nhân sự trong cơ sở dữ liệu
                            </div>
                          )}

                          {/* Metric Pills */}
                          <div className="metric-pills">
                            <span className="pill">📐 {f.metrics.width_px}×{f.metrics.height_px}px</span>
                            <span className="pill">✨ Nét: {f.metrics.laplacian_variance}</span>
                            <span className="pill">☀️ Sáng: {f.metrics.brightness}</span>
                            <span className={'pill ' + (f.status === 'acceptable' ? 'pill-ok' : 'pill-warn')}>
                              {f.status === 'acceptable' ? 'Đạt chuẩn' : 'Cần xem lại'}
                            </span>
                          </div>
                        </div>
                      ))
                    )}
                  </>
                )}
              </section>
            </div>

            <CaseHistory refreshKey={result?.case_id} />
          </>
        )}

        {/* TAB 2: PERSONNEL DIRECTORY (ADMIN ONLY) */}
        {tab === 'people' && isAdmin && (
          <>
            <div className="toolbar-sticky">
              <div className="toolbar">
                <div className="search-box">
                  <Search size={16} color="#64748b" />
                  <input
                    ref={searchInputRef}
                    type="search"
                    inputMode="search"
                    enterKeyHint="search"
                    aria-label="Tìm nhân sự"
                    placeholder="Tìm tên, mã NV, phòng ban…"
                    value={query}
                    onChange={e => {
                      setQuery(e.target.value);
                      setPage(0);
                    }}
                  />
                  {query && (
                    <button
                      className="search-clear"
                      onClick={() => {
                        setQuery('');
                        searchInputRef.current?.focus();
                      }}
                    >
                      <X size={15} />
                    </button>
                  )}
                </div>
                <button className="primary" onClick={() => setEditing({})}>
                  <Plus size={15} />
                  <span>Thêm</span>
                </button>
              </div>

              <div className="filter-chips">
                {[
                  ['all', 'Tất cả (' + list.total.toLocaleString('vi-VN') + ')'],
                  ['tech', 'Khối Công nghệ'],
                  ['office', 'Văn phòng']
                ].map(([val, label]) => (
                  <button
                    key={val}
                    className={'chip ' + (filterChip === val ? 'active' : '')}
                    onClick={() => {
                      setFilterChip(val);
                      setPage(0);
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid">
              {list.items.map(p => (
                <button className="person card" key={p.id} onClick={() => setEditing(p)}>
                  {p.photo_url ? (
                    <img loading="lazy" src={p.photo_url} alt={p.name} />
                  ) : (
                    <div className="avatar">
                      <Users size={18} />
                    </div>
                  )}
                  <div className="person-info">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <strong>{p.name}</strong>
                      <span className="badge-code">{p.employee_id}</span>
                    </div>
                    <p>{p.title || 'Nhân viên'}</p>
                    <small>{p.department || p.division || ''}</small>
                  </div>
                </button>
              ))}
            </div>

            <footer>
              <button disabled={!page} onClick={() => setPage(page - 1)}>
                <ChevronLeft size={15} />
                Trước
              </button>
              <span>
                {page + 1} / {Math.max(1, Math.ceil(list.total / 24))}
              </span>
              <button disabled={(page + 1) * 24 >= list.total} onClick={() => setPage(page + 1)}>
                Sau
                <ChevronRight size={15} />
              </button>
            </footer>
          </>
        )}

        {/* TAB 3: SYSTEM STATUS */}
        {tab === 'api' && (
          <section className="card" style={{ padding: '20px' }}>
            <h2 style={{ fontSize: '15px' }}>Trạng thái mô hình AI</h2>
            <pre>{JSON.stringify(health, null, 2)}</pre>
            <a className="primary link" href="/docs" target="_blank" rel="noreferrer" style={{ marginTop: '12px' }}>
              <Code size={15} />
              Tài liệu API Swagger
            </a>
          </section>
        )}
      </main>

      {/* Bottom Nav for Mobile */}
      <div className="mobile-nav">
        {navItems.map(([id, Icon, label]) => (
          <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>
            <Icon />
            <span>{label}</span>
          </button>
        ))}
        <button onClick={() => setChangingPassword(true)}>
          <KeyRound size={18} />
          <span>Mật khẩu</span>
        </button>
        <button onClick={handleLogout}>
          <LogOut size={18} />
          <span>Thoát</span>
        </button>
      </div>

      {/* Edit Person Modal (Admin) */}
      <dialog ref={dialog} onCancel={() => setEditing(null)} aria-labelledby="person-title">
        {editing && (
          <form onSubmit={save}>
            <h2 id="person-title">{editing.id ? 'Hồ sơ nhân sự' : 'Thêm nhân sự'}</h2>
            {[
              ['name', 'Họ và tên'],
              ['employee_id', 'Mã nhân viên'],
              ['title', 'Chức danh'],
              ['department', 'Phòng ban'],
              ['division', 'Khối / Ban']
            ].map(([key, label]) => (
              <label className="field" key={key}>
                {label}
                <input
                  name={key}
                  defaultValue={editing[key] || ''}
                  required={['name', 'employee_id'].includes(key)}
                  maxLength={key === 'employee_id' ? 100 : key === 'name' ? 200 : 300}
                />
              </label>
            ))}
            <footer>
              <button type="button" onClick={() => setEditing(null)}>
                Đóng
              </button>
              <button className="primary" disabled={busy}>
                <Save size={15} />
                {busy ? 'Đang lưu…' : 'Lưu'}
              </button>
            </footer>
          </form>
        )}
      </dialog>

      {/* Password Modal */}
      <dialog ref={pwdDialog} onCancel={() => setChangingPassword(false)}>
        {changingPassword && (
          <form onSubmit={handleChangePassword}>
            <h2>Đổi mật khẩu</h2>
            <label className="field">
              Mật khẩu cũ
              <input type="password" name="old_password" required autoFocus />
            </label>
            <label className="field">
              Mật khẩu mới
              <input type="password" name="new_password" required minLength={4} />
            </label>
            <label className="field">
              Nhập lại mật khẩu mới
              <input type="password" name="confirm_password" required minLength={4} />
            </label>
            <footer>
              <button type="button" onClick={() => setChangingPassword(false)}>
                Hủy
              </button>
              <button className="primary" disabled={busy}>
                <KeyRound size={15} />
                {busy ? 'Đang lưu…' : 'Cập nhật'}
              </button>
            </footer>
          </form>
        )}
      </dialog>

      {toast && (
        <div className="toast" role="status" onClick={() => setToast('')}>
          {toast}
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
