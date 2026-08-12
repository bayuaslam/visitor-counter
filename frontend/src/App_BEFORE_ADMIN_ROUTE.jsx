import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  Bell,
  Box,
  CalendarDays,
  CheckCircle2,
  Circle,
  Clock3,
  ChevronRight,
  ClipboardCheck,
  DoorOpen,
  FlaskConical,
  Home,
  LayoutDashboard,
  MapPin,
  Menu,
  PackageOpen,
  Printer,
  Search,
  Send,
  Sheet,
  Pencil,
  Plus,
  Trash2,
  UserCog,
  Users,
  WifiOff,
  Wrench,
  X,
} from "lucide-react";

const navItems = [
  { id: "dashboard", label: "Dashboard Umum", icon: Home },
  { id: "equipment", label: "Daftar Alat", icon: Box },
  { id: "loans", label: "Peminjaman Alat", icon: ClipboardCheck },
  { id: "rooms", label: "Booking Ruangan", icon: CalendarDays },
  { id: "printing", label: "3D Printing", icon: Printer },
  { id: "maintenance", label: "Laporan Kerusakan", icon: Wrench },
];

const serviceConfig = {
  loans: { type: "EQUIPMENT_LOAN", eyebrow: "PEMINJAMAN ALAT", title: "Ajukan peminjaman", description: "Pilih alat, tentukan periode, lalu pantau proses persetujuannya.", icon: ClipboardCheck, steps: ["PENDING", "APPROVED", "BORROWED", "RETURNED"] },
  rooms: { type: "ROOM_BOOKING", eyebrow: "BOOKING RUANGAN", title: "Pesan ruangan lab", description: "Ajukan jadwal penggunaan ruangan tanpa risiko double booking.", icon: CalendarDays, steps: ["PENDING", "APPROVED", "COMPLETED"] },
  printing: { type: "PRINT_3D", eyebrow: "LAYANAN 3D PRINTING", title: "Ajukan pencetakan", description: "Kirim detail proyek dan pantau antrean produksi dari review sampai pengambilan.", icon: Printer, steps: ["SUBMITTED", "REVIEW", "APPROVED", "QUEUED", "PRINTING", "FINISHED", "PICKED_UP"] },
  maintenance: { type: "MAINTENANCE", eyebrow: "MAINTENANCE", title: "Laporkan kerusakan", description: "Laporkan kondisi alat agar laboran dapat menindaklanjuti dengan cepat.", icon: Wrench, steps: ["REPORTED", "CHECKING", "REPAIRING", "COMPLETED"] },
};

const allStatusFlows = {
  EQUIPMENT_LOAN: ["PENDING", "APPROVED", "BORROWED", "RETURNED", "REJECTED"],
  ROOM_BOOKING: ["PENDING", "APPROVED", "COMPLETED", "REJECTED", "CANCELLED"],
  PRINT_3D: ["SUBMITTED", "REVIEW", "APPROVED", "QUEUED", "PRINTING", "FINISHED", "PICKED_UP", "REJECTED"],
  MAINTENANCE: ["REPORTED", "CHECKING", "REPAIRING", "COMPLETED", "UNREPAIRABLE"],
};

const canonicalSteps = ["Pengajuan", "Diperiksa", "Diproses", "Selesai"];

function progressIndex(request) {
  const status = request.status;
  if (["REJECTED", "CANCELLED", "UNREPAIRABLE"].includes(status)) return 0;
  if (["RETURNED", "COMPLETED", "FINISHED", "PICKED_UP"].includes(status)) return 3;
  if (["APPROVED", "BORROWED", "QUEUED", "PRINTING", "REPAIRING"].includes(status)) return 2;
  if (["REVIEW", "CHECKING"].includes(status)) return 1;
  return 0;
}

const apiHeaders = (role) => ({
  "Content-Type": "application/json",
  "X-LabHub-Role": role,
  "X-LabHub-User": role === "LABORAN" ? "laboran.demo" : "student.demo",
  "X-LabHub-Name": role === "LABORAN" ? "Laboran Demo" : "Mahasiswa Demo",
});

function formatTime(value) {
  if (!value) return "Belum ada aktivitas";
  const parsed = new Date(value.replace(" ", "T"));
  return new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(parsed);
}

function MetricCard({ label, value, icon: Icon, tone, detail }) {
  return (
    <article className={`metric-card metric-${tone}`}>
      <div className="metric-icon"><Icon size={21} strokeWidth={2} /></div>
      <div className="metric-copy">
        <p>{label}</p>
        <strong>{value ?? "—"}</strong>
        <span>{detail}</span>
      </div>
    </article>
  );
}

function Dashboard({ onOpenEquipment }) {
  const [data, setData] = useState(null);
  const [recent, setRecent] = useState([]);
  const [error, setError] = useState("");
  const [lastSync, setLastSync] = useState(null);
  const [studentRequests, setStudentRequests] = useState([]);

  const loadDashboard = useCallback(async () => {
    try {
      const [summaryResponse, recentResponse, requestsResponse] = await Promise.all([
        fetch("/api/visitors", { cache: "no-store" }),
        fetch("/api/visitors/recent?limit=5", { cache: "no-store" }),
        fetch("/api/requests", { headers: apiHeaders("STUDENT"), cache: "no-store" }),
      ]);
      if (!summaryResponse.ok || !recentResponse.ok || !requestsResponse.ok) throw new Error();
      const [summary, events] = await Promise.all([
        summaryResponse.json(),
        recentResponse.json(),
      ]);
      setData(summary);
      setRecent(events.events ?? []);
      setStudentRequests(await requestsResponse.json());
      setLastSync(new Date());
      setError("");
    } catch {
      setError("Data visitor belum dapat diperbarui. Mencoba lagi otomatis…");
    }
  }, []);

  useEffect(() => {
    loadDashboard();
    const interval = window.setInterval(loadDashboard, 3000);
    return () => window.clearInterval(interval);
  }, [loadDashboard]);

  return (
    <>
      <section className="welcome">
        <div>
          <p className="eyebrow">LAB ROBOTIKA & INOVASI</p>
          <h1>Selamat datang di Lab Robotika & Inovasi</h1>
          <p>Pantau aktivitas laboratorium dan akses seluruh layanan dalam satu tempat.</p>
        </div>
        <div className={`live-pill ${error ? "live-error" : ""}`}>
          <span />{error ? "Koneksi terganggu" : "Live · diperbarui otomatis"}
        </div>
      </section>

      {error && <div className="error-banner" role="status">{error}</div>}

      <section className="metrics" aria-label="Statistik visitor">
        <MetricCard label="People Inside" value={data?.inside} icon={Users} tone="green" detail="Saat ini di dalam lab" />
        <MetricCard label="Visitors Today" value={data?.today_in} icon={Activity} tone="blue" detail="Total pengunjung masuk" />
        <MetricCard label="Today IN" value={data?.today_in} icon={ArrowDownLeft} tone="teal" detail="Masuk hari ini" />
        <MetricCard label="Today OUT" value={data?.today_out} icon={ArrowUpRight} tone="amber" detail="Keluar hari ini" />
      </section>

      <section className="dashboard-grid">
        <article className="panel occupancy-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">KONDISI RUANGAN</p><h2>Status laboratorium</h2></div>
            <span className="open-badge"><DoorOpen size={15} /> Buka</span>
          </div>
          <div className="occupancy-body">
            <div className="occupancy-number"><strong>{data?.inside ?? "—"}</strong><span>orang di dalam</span></div>
            <div className="occupancy-copy">
              <p>Aktivitas terakhir</p>
              <strong>{data?.last_event ? `${data.last_event} · ${formatTime(data.last_event_time)}` : "Belum ada aktivitas"}</strong>
              <span>Pembaruan terakhir {lastSync ? formatTime(lastSync.toISOString()) : "—"}</span>
            </div>
          </div>
        </article>

        <article className="panel recent-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">REALTIME</p><h2>Aktivitas terbaru</h2></div>
            <button className="text-button" onClick={loadDashboard}>Perbarui</button>
          </div>
          <div className="event-list">
            {recent.length === 0 && <p className="empty-state">Belum ada event visitor.</p>}
            {recent.map((event) => (
              <div className="event-row" key={event.id}>
                <span className={`event-icon ${event.direction === "IN" ? "event-in" : "event-out"}`}>
                  {event.direction === "IN" ? <ArrowDownLeft size={17} /> : <ArrowUpRight size={17} />}
                </span>
                <div><strong>Visitor {event.direction}</strong><small>{formatTime(event.timestamp)}</small></div>
                <span className="inside-count">{event.occupancy_after} di dalam</span>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="panel general-progress-panel">
        <div className="panel-heading"><div><p className="eyebrow">PROGRESS PENGAJUAN</p><h2>Status layanan terbaru</h2></div><span className="request-total">{studentRequests.length}</span></div>
        <div className="general-progress-list">
          {studentRequests.length === 0 && <div className="compact-empty compact-empty-short"><Clock3 size={24} /><strong>Belum ada pengajuan</strong><p>Progress peminjaman, ruangan, 3D printing, dan maintenance akan tampil di sini.</p></div>}
          {studentRequests.slice(0, 4).map((request) => <article className="general-progress-row" key={request.id}><div><small>{request.request_type.replaceAll("_", " ")}</small><strong>{request.title}</strong></div><ProgressTracker request={request} /></article>)}
        </div>
      </section>

      <section className="quick-section">
        <div className="section-heading"><p className="eyebrow">LAYANAN LAB</p><h2>Akses cepat</h2></div>
        <div className="quick-grid">
          <button className="quick-card quick-card-live" onClick={onOpenEquipment}>
            <span><Box size={20} /></span><div><strong>Daftar alat</strong><small>Cari dan cek ketersediaan alat</small></div><ChevronRight size={18} />
          </button>
          {[
            [CalendarDays, "Booking ruangan", "Lihat jadwal penggunaan lab"],
            [Printer, "Layanan 3D printing", "Kirim dan pantau antrean cetak"],
            [ClipboardCheck, "Laporan kerusakan", "Laporkan masalah peralatan"],
          ].map(([Icon, title, description]) => (
            <button className="quick-card" key={title} disabled title="Segera hadir">
              <span><Icon size={20} /></span><div><strong>{title}</strong><small>{description}</small></div><ChevronRight size={18} />
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

function EquipmentCatalog() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [availability, setAvailability] = useState("");
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/equipment/summary", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then(setSummary)
      .catch(() => setError("Ringkasan inventory belum dapat dimuat."));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      if (category) params.set("category", category);
      if (availability) params.set("availability", availability);
      try {
        const response = await fetch(`/api/equipment?${params}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) throw new Error();
        const result = await response.json();
        setItems(result.items ?? []);
        setError("");
      } catch (requestError) {
        if (requestError.name !== "AbortError") setError("Daftar alat belum dapat dimuat.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, category, availability]);

  const hasFilters = Boolean(query || category || availability);
  const categories = useMemo(() => summary?.categories ?? [], [summary]);

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">INVENTORY LAB</p>
          <h1>Daftar alat</h1>
          <p>Temukan peralatan dan periksa stok yang tersedia sebelum mengajukan peminjaman.</p>
        </div>
      </section>

      <section className="inventory-summary" aria-label="Ringkasan inventory">
        <div><span>Total aset</span><strong>{summary?.total_assets ?? "—"}</strong></div>
        <div><span>Total unit</span><strong>{summary?.total_units ?? "—"}</strong></div>
        <div><span>Tersedia</span><strong className="summary-available">{summary?.available_units ?? "—"}</strong></div>
        <div><span>Sedang digunakan</span><strong>{summary?.unavailable_units ?? "—"}</strong></div>
      </section>

      <section className="catalog-panel">
        <div className="catalog-toolbar">
          <label className="search-field">
            <Search size={18} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Cari nama, kode aset, atau kategori" aria-label="Cari alat" />
            {query && <button onClick={() => setQuery("")} aria-label="Hapus pencarian"><X size={16} /></button>}
          </label>
          <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Filter kategori">
            <option value="">Semua kategori</option>
            {categories.map((item) => <option value={item} key={item}>{item}</option>)}
          </select>
          <select value={availability} onChange={(event) => setAvailability(event.target.value)} aria-label="Filter ketersediaan">
            <option value="">Semua stok</option>
            <option value="available">Tersedia</option>
            <option value="unavailable">Tidak tersedia</option>
          </select>
        </div>

        {error && <div className="error-banner catalog-error"><WifiOff size={16} />{error}</div>}

        {loading ? (
          <div className="catalog-loading" role="status"><span /><p>Memuat daftar alat…</p></div>
        ) : items.length === 0 ? (
          <div className="catalog-empty">
            <span><PackageOpen size={30} /></span>
            <h2>{hasFilters ? "Alat tidak ditemukan" : "Inventory masih kosong"}</h2>
            <p>{hasFilters ? "Coba ubah kata kunci atau filter pencarian." : "Data alat akan tampil di sini setelah ditambahkan oleh laboran."}</p>
            {hasFilters && <button className="secondary-button" onClick={() => { setQuery(""); setCategory(""); setAvailability(""); }}>Reset filter</button>}
          </div>
        ) : (
          <div className="equipment-grid">
            {items.map((item) => (
              <article className="equipment-card" key={item.id}>
                <div className="equipment-visual"><Box size={30} /><span>{item.category}</span></div>
                <div className="equipment-content">
                  <div className="equipment-title"><div><small>{item.asset_code}</small><h2>{item.name}</h2></div><span className={`condition condition-${item.condition.toLowerCase()}`}>{item.condition}</span></div>
                  <p className="equipment-description">{item.description || "Belum ada deskripsi alat."}</p>
                  <div className="equipment-meta"><span><MapPin size={14} />{item.location || "Lokasi belum diatur"}</span><span><CheckCircle2 size={14} />{item.quantity_available} dari {item.quantity_total} tersedia</span></div>
                  <div className="stock-bar" aria-label={`${item.quantity_available} dari ${item.quantity_total} tersedia`}><span style={{ width: `${item.quantity_total ? (item.quantity_available / item.quantity_total) * 100 : 0}%` }} /></div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function ProgressTracker({ request }) {
  const terminalFailure = ["REJECTED", "CANCELLED", "UNREPAIRABLE"].includes(request.status);
  const activeIndex = progressIndex(request);
  return (
    <div className={`progress-tracker ${terminalFailure ? "tracker-failed" : ""}`}>
      {canonicalSteps.map((step, index) => {
        const complete = !terminalFailure && activeIndex >= index;
        const current = request.status === step;
        return (
          <div className={`progress-step ${complete ? "step-complete" : ""} ${current ? "step-current" : ""}`} key={step}>
            <span>{complete ? <CheckCircle2 size={16} /> : <Circle size={14} />}</span>
            <small>{step.replaceAll("_", " ")}</small>
          </div>
        );
      })}
      {terminalFailure && <div className="failure-label">{request.status.replaceAll("_", " ")}</div>}
    </div>
  );
}

function ServiceWorkspace({ page, role }) {
  const config = serviceConfig[page];
  const Icon = config.icon;
  const [requests, setRequests] = useState([]);
  const [form, setForm] = useState({ title: "", description: "", equipment_id: "", room_name: "Lab Utama", start_at: "", end_at: "", quantity: 1, material: "PLA", color: "Putih", infill: 20, participants: 1 });
  const [file, setFile] = useState(null);
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const loadRequests = useCallback(async () => {
    const response = await fetch(`/api/requests?request_type=${config.type}`, { headers: apiHeaders(role), cache: "no-store" });
    if (response.ok) setRequests(await response.json());
  }, [config.type, role]);

  useEffect(() => { loadRequests(); }, [loadRequests]);

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    const payload = {
      request_type: config.type,
      title: form.title,
      description: form.description || null,
      equipment_id: form.equipment_id ? Number(form.equipment_id) : null,
      room_name: config.type === "ROOM_BOOKING" ? form.room_name : null,
      start_at: form.start_at ? (config.type === "EQUIPMENT_LOAN" ? `${form.start_at}T00:00:00` : form.start_at) : null,
      end_at: form.end_at ? (config.type === "EQUIPMENT_LOAN" ? `${form.end_at}T23:59:00` : form.end_at) : null,
      quantity: Number(form.quantity) || 1,
      details: config.type === "PRINT_3D" ? { material: form.material, color: form.color, infill: Number(form.infill) } : config.type === "ROOM_BOOKING" ? { participants: Number(form.participants) } : {},
    };
    try {
      const response = await fetch("/api/requests", { method: "POST", headers: apiHeaders(role), body: JSON.stringify(payload) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Request gagal dikirim");
      if (file && ["PRINT_3D", "MAINTENANCE"].includes(config.type)) {
        const uploadData = new FormData();
        uploadData.append("upload", file);
        const uploadResponse = await fetch(`/api/requests/${result.id}/file`, { method: "POST", headers: { "X-LabHub-Role": role, "X-LabHub-User": "student.demo", "X-LabHub-Name": "Mahasiswa Demo" }, body: uploadData });
        if (!uploadResponse.ok) throw new Error((await uploadResponse.json()).detail || "File gagal diunggah");
      }
      setForm((current) => ({ ...current, title: "", description: "" }));
      setFile(null);
      setMessage("Request berhasil dikirim dan progress tracker sudah aktif.");
      await loadRequests();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <section className="page-heading service-heading"><div><p className="eyebrow">{config.eyebrow}</p><h1>{config.title}</h1><p>{config.description}</p></div><span className="service-icon"><Icon size={24} /></span></section>
      <section className="service-layout">
        <form className="request-form panel" onSubmit={submit}>
          <div className="panel-heading"><div><p className="eyebrow">FORM REQUEST</p><h2>Detail pengajuan</h2></div></div>
          <label>Nama project / keperluan<input required value={form.title} onChange={(event) => update("title", event.target.value)} maxLength={200} /></label>
          {(config.type === "EQUIPMENT_LOAN" || config.type === "MAINTENANCE") && <label>ID alat<input required type="number" min="1" value={form.equipment_id} onChange={(event) => update("equipment_id", event.target.value)} placeholder="Masukkan ID dari Daftar Alat" /></label>}
          {config.type === "ROOM_BOOKING" && <><label>Ruangan<select value={form.room_name} onChange={(event) => update("room_name", event.target.value)}><option>Lab Utama</option><option>Ruang Diskusi</option><option>Area Workshop</option></select></label><label>Jumlah peserta<input type="number" min="1" max="100" value={form.participants} onChange={(event) => update("participants", event.target.value)} /></label></>}
          {(config.type === "EQUIPMENT_LOAN" || config.type === "ROOM_BOOKING") && <div className="form-row"><label>Mulai<input required type={config.type === "ROOM_BOOKING" ? "datetime-local" : "date"} value={form.start_at} onChange={(event) => update("start_at", event.target.value)} /></label><label>Selesai<input required type={config.type === "ROOM_BOOKING" ? "datetime-local" : "date"} value={form.end_at} onChange={(event) => update("end_at", event.target.value)} /></label></div>}
          {config.type === "PRINT_3D" && <><div className="form-row"><label>Material<select value={form.material} onChange={(event) => update("material", event.target.value)}><option>PLA</option><option>PETG</option><option>ABS</option><option>TPU</option></select></label><label>Warna<input value={form.color} onChange={(event) => update("color", event.target.value)} /></label></div><div className="form-row"><label>Quantity<input type="number" min="1" max="100" value={form.quantity} onChange={(event) => update("quantity", event.target.value)} /></label><label>Infill (%)<input type="number" min="0" max="100" value={form.infill} onChange={(event) => update("infill", event.target.value)} /></label></div><label>File desain (.stl / .3mf)<input required type="file" accept=".stl,.3mf" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label></>}
          {config.type === "MAINTENANCE" && <label>Foto kerusakan (opsional)<input type="file" accept=".jpg,.jpeg,.png,.webp" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>}
          <label>Catatan<textarea rows="4" value={form.description} onChange={(event) => update("description", event.target.value)} maxLength={2000} /></label>
          {message && <div className={`form-message ${message.startsWith("Request berhasil") ? "message-success" : ""}`}>{message}</div>}
          <button className="primary-button" disabled={submitting}><Send size={16} />{submitting ? "Mengirim…" : "Kirim request"}</button>
        </form>

        <div className="request-history panel">
          <div className="panel-heading"><div><p className="eyebrow">PROGRESS TRACKER</p><h2>Riwayat pengajuan</h2></div><span className="request-total">{requests.length}</span></div>
          <div className="request-list">
            {requests.length === 0 && <div className="compact-empty"><Clock3 size={25} /><strong>Belum ada pengajuan</strong><p>Request yang dikirim akan muncul di sini lengkap dengan progresnya.</p></div>}
            {requests.map((request) => <article className="request-card" key={request.id}><div className="request-card-head"><div><small>{request.request_code}</small><h3>{request.title}</h3></div><span className="status-badge">{request.status.replaceAll("_", " ")}</span></div><ProgressTracker request={request} /><div className="request-footer"><span>Dibuat {new Date(request.created_at).toLocaleDateString("id-ID")}</span>{request.admin_note && <span>Catatan: {request.admin_note}</span>}</div></article>)}
          </div>
        </div>
      </section>
    </>
  );
}

function LaboranInventory({ role }) {
  const emptyForm = { asset_code: "", name: "", category: "", quantity_total: 1, quantity_available: 1, condition: "GOOD", location: "", description: "" };
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [message, setMessage] = useState("");
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    const response = await fetch("/api/equipment?page_size=100", { cache: "no-store" });
    if (response.ok) setItems((await response.json()).items ?? []);
  }, []);
  useEffect(() => { load(); }, [load]);

  const startAdd = () => { setForm(emptyForm); setEditingId(null); setFormOpen(true); setMessage(""); };
  const startEdit = (item) => { setForm({ asset_code: item.asset_code, name: item.name, category: item.category, quantity_total: item.quantity_total, quantity_available: item.quantity_available, condition: item.condition, location: item.location, description: item.description || "" }); setEditingId(item.id); setFormOpen(true); setMessage(""); };
  const save = async (event) => {
    event.preventDefault();
    const response = await fetch(editingId ? `/api/laboran/equipment/${editingId}` : "/api/laboran/equipment", { method: editingId ? "PATCH" : "POST", headers: apiHeaders(role), body: JSON.stringify({ ...form, quantity_total: Number(form.quantity_total), quantity_available: Number(form.quantity_available) }) });
    const result = response.status === 204 ? {} : await response.json();
    if (!response.ok) { setMessage(result.detail || "Data alat gagal disimpan"); return; }
    setMessage(editingId ? "Data alat diperbarui." : "Alat baru ditambahkan."); setFormOpen(false); await load();
  };
  const remove = async (item) => {
    if (!window.confirm(`Hapus ${item.name}?`)) return;
    const response = await fetch(`/api/laboran/equipment/${item.id}`, { method: "DELETE", headers: apiHeaders(role) });
    if (!response.ok) { setMessage((await response.json()).detail || "Alat gagal dihapus"); return; }
    setMessage("Alat berhasil dihapus."); await load();
  };
  const importExcel = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const data = new FormData(); data.append("upload", file);
    const response = await fetch("/api/laboran/equipment/import", { method: "POST", headers: { "X-LabHub-Role": role, "X-LabHub-User": "laboran.demo", "X-LabHub-Name": "Laboran Demo" }, body: data });
    const result = await response.json();
    setMessage(response.ok ? `Import selesai: ${result.imported} baru, ${result.updated} diperbarui, ${result.skipped} dilewati.` : result.detail || "Import gagal");
    event.target.value = ""; if (response.ok) await load();
  };

  return <section className="panel inventory-manager">
    <div className="inventory-manager-head"><div><p className="eyebrow">INVENTORY MANAGEMENT</p><h2>Daftar alat laboratorium</h2><span>{items.length} aset terdaftar</span></div><div className="inventory-actions"><input ref={fileRef} type="file" accept=".xlsx" hidden onChange={importExcel} /><button className="secondary-action" onClick={() => fileRef.current?.click()}><Sheet size={15} /> Import Excel</button><button className="primary-action" onClick={startAdd}><Plus size={15} /> Tambah alat</button></div></div>
    {message && <div className="inventory-message">{message}</div>}
    {formOpen && <form className="equipment-editor" onSubmit={save}><div className="editor-grid"><label>Kode aset<input required value={form.asset_code} onChange={(e) => setForm({ ...form, asset_code: e.target.value })} /></label><label>Nama alat<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label><label>Kategori<input required value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></label><label>Lokasi<input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></label><label>Total unit<input required type="number" min="0" value={form.quantity_total} onChange={(e) => setForm({ ...form, quantity_total: e.target.value })} /></label><label>Unit tersedia<input required type="number" min="0" value={form.quantity_available} onChange={(e) => setForm({ ...form, quantity_available: e.target.value })} /></label><label>Kondisi<select value={form.condition} onChange={(e) => setForm({ ...form, condition: e.target.value })}><option>GOOD</option><option>MAINTENANCE</option><option>DAMAGED</option><option>BROKEN</option></select></label><label className="editor-description">Deskripsi<textarea rows="2" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label></div><div className="editor-actions"><button type="button" onClick={() => setFormOpen(false)}>Batal</button><button type="submit">Simpan alat</button></div></form>}
    <div className="inventory-table"><div className="inventory-table-row inventory-table-header"><span>Kode</span><span>Nama alat</span><span>Kategori</span><span>Stok</span><span>Aksi</span></div>{items.length === 0 && <div className="inventory-table-empty">Belum ada alat. Tambahkan manual atau import Excel.</div>}{items.slice(0, 12).map((item) => <div className="inventory-table-row" key={item.id}><span>{item.asset_code}</span><strong>{item.name}</strong><span>{item.category}</span><span>{item.quantity_available}/{item.quantity_total}</span><span className="row-actions"><button onClick={() => startEdit(item)} aria-label={`Edit ${item.name}`}><Pencil size={14} /></button><button className="delete-action" onClick={() => remove(item)} aria-label={`Hapus ${item.name}`}><Trash2 size={14} /></button></span></div>)}</div>
    <p className="import-hint">Kolom Excel: asset_code, name, category, quantity_total, quantity_available, condition, location, description.</p>
  </section>;
}

function LaboranDashboard({ role }) {
  const [requests, setRequests] = useState([]);
  const [counts, setCounts] = useState([]);
  const [filter, setFilter] = useState("");
  const [selectedStatus, setSelectedStatus] = useState({});

  const load = useCallback(async () => {
    const suffix = filter ? `?request_type=${filter}` : "";
    const [requestResponse, summaryResponse] = await Promise.all([
      fetch(`/api/laboran/requests${suffix}`, { headers: apiHeaders(role), cache: "no-store" }),
      fetch("/api/laboran/summary", { headers: apiHeaders(role), cache: "no-store" }),
    ]);
    if (requestResponse.ok) setRequests(await requestResponse.json());
    if (summaryResponse.ok) setCounts((await summaryResponse.json()).counts ?? []);
  }, [filter, role]);

  useEffect(() => { load(); }, [load]);

  const updateStatus = async (request, forcedStatus = null) => {
    const status = forcedStatus || selectedStatus[request.id] || request.status;
    await fetch(`/api/laboran/requests/${request.id}`, { method: "PATCH", headers: apiHeaders(role), body: JSON.stringify({ status }) });
    await load();
  };

  const pending = counts.filter((item) => ["PENDING", "SUBMITTED", "REPORTED", "REVIEW"].includes(item.status)).reduce((sum, item) => sum + item.count, 0);
  const active = counts.filter((item) => ["APPROVED", "BORROWED", "QUEUED", "PRINTING", "CHECKING", "REPAIRING"].includes(item.status)).reduce((sum, item) => sum + item.count, 0);

  return (
    <>
      <section className="page-heading service-heading"><div><p className="eyebrow">DASHBOARD LABORAN</p><h1>Pusat operasional lab</h1><p>Kelola approval, antrean layanan, dan tindak lanjut dari satu ruang kerja.</p></div><span className="service-icon"><UserCog size={24} /></span></section>
      <section className="laboran-metrics"><MetricCard label="Menunggu tindakan" value={pending} icon={Clock3} tone="amber" detail="Request baru dan review" /><MetricCard label="Sedang berjalan" value={active} icon={Activity} tone="green" detail="Layanan aktif" /><MetricCard label="Total request" value={requests.length} icon={LayoutDashboard} tone="blue" detail="Sesuai filter saat ini" /></section>
      <LaboranInventory role={role} />
      <section className="panel laboran-panel">
        <div className="laboran-toolbar"><div><p className="eyebrow">WORK QUEUE</p><h2>Antrean layanan</h2></div><select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">Semua layanan</option><option value="EQUIPMENT_LOAN">Peminjaman</option><option value="ROOM_BOOKING">Booking ruangan</option><option value="PRINT_3D">3D printing</option><option value="MAINTENANCE">Maintenance</option></select></div>
        <div className="laboran-list">
          {requests.length === 0 && <div className="compact-empty"><CheckCircle2 size={27} /><strong>Antrean bersih</strong><p>Belum ada request pada filter ini.</p></div>}
          {requests.map((request) => <article className="laboran-row" key={request.id}>
            <div className="laboran-request"><small>{request.request_code} · {request.request_type.replaceAll("_", " ")}</small><strong>{request.title}</strong><span>{request.requester_name} · {new Date(request.created_at).toLocaleString("id-ID")}</span><ProgressTracker request={request} /></div>
            <span className="status-badge">{request.status}</span>
            <div className="status-action">
              {["EQUIPMENT_LOAN", "ROOM_BOOKING", "PRINT_3D"].includes(request.request_type) && ["PENDING", "SUBMITTED", "REVIEW"].includes(request.status) && <div className="decision-buttons"><button className="accept-button" onClick={() => updateStatus(request, "APPROVED")}><CheckCircle2 size={14} /> Accept</button><button className="reject-button" onClick={() => updateStatus(request, "REJECTED")}><X size={14} /> Reject</button></div>}
              <div className="manual-status"><select value={selectedStatus[request.id] || request.status} onChange={(event) => setSelectedStatus((current) => ({ ...current, [request.id]: event.target.value }))}>{allStatusFlows[request.request_type].map((status) => <option value={status} key={status}>{status.replaceAll("_", " ")}</option>)}</select><button onClick={() => updateStatus(request)}>Simpan</button></div>
            </div>
          </article>)}
        </div>
      </section>
    </>
  );
}

function App() {
  const [page, setPage] = useState("laboran");
  const [menuOpen, setMenuOpen] = useState(false);

  const navigate = (nextPage) => {
    setPage(nextPage);
    setMenuOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const renderPage = () => {
    if (page === "dashboard") return <Dashboard onOpenEquipment={() => navigate("equipment")} />;
    if (page === "equipment") return <EquipmentCatalog />;
    if (page === "laboran") return <LaboranDashboard role="LABORAN" />;
    if (serviceConfig[page]) return <ServiceWorkspace page={page} role="STUDENT" />;
    return <Dashboard onOpenEquipment={() => navigate("equipment")} />;
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <img className="sidebar-logo" src="/electrical-engineering-logo.webp" alt="Department of Electrical Engineering" />
          <button className="icon-button close-menu" onClick={() => setMenuOpen(false)} aria-label="Tutup menu"><X /></button>
        </div>
        <nav aria-label="Navigasi utama">
          <p className="nav-label">Menu utama</p>
          <button className={page === "laboran" ? "nav-active" : ""} onClick={() => navigate("laboran")}><LayoutDashboard size={19} /><span>Dashboard Laboran</span></button>
          {navItems.map(({ id, label, icon: Icon, upcoming }) => (
            <button key={id} className={page === id ? "nav-active" : ""} disabled={upcoming} onClick={() => navigate(id)} title={upcoming ? "Segera hadir" : undefined}>
              <Icon size={19} /><span>{label}</span>{upcoming && <small>Segera</small>}
            </button>
          ))}
        </nav>
        <div className="lab-status"><span className="status-dot" /><div><strong>Lab aktif</strong><small>Visitor counter terhubung</small></div></div>
      </aside>

      {menuOpen && <button className="backdrop" onClick={() => setMenuOpen(false)} aria-label="Tutup menu" />}

      <main>
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setMenuOpen(true)} aria-label="Buka menu"><Menu /></button>
          <div className="top-actions"><button className="icon-button" aria-label="Notifikasi"><Bell size={20} /></button><div className="avatar">LB</div></div>
        </header>
        <div className="content">
          {renderPage()}
        </div>
      </main>

      <nav className="mobile-nav" aria-label="Navigasi mobile">
        <button className={page === "dashboard" ? "mobile-active" : ""} onClick={() => navigate("dashboard")}><Home size={20} /><span>Home</span></button>
        <button className={page === "equipment" ? "mobile-active" : ""} onClick={() => navigate("equipment")}><Box size={20} /><span>Alat</span></button>
        <button className={page === "rooms" ? "mobile-active" : ""} onClick={() => navigate("rooms")}><CalendarDays size={20} /><span>Ruangan</span></button>
        <button className={page === "laboran" ? "mobile-active" : ""} onClick={() => navigate("laboran")}><Users size={20} /><span>Laboran</span></button>
      </nav>
    </div>
  );
}

export default App;
