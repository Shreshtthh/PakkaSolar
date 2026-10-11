import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  UploadCloud, CheckCircle2, XCircle, AlertTriangle,
  ShieldCheck, Zap, Receipt, Volume2, ScanLine,
  BadgeCheck, Lock, ArrowRight, RefreshCw
} from 'lucide-react';
import imageCompression from 'browser-image-compression';
import { motion, AnimatePresence } from 'framer-motion';
import './index.css';

const API_URL = "https://7a8zj1nbya.execute-api.ap-south-1.amazonaws.com/prod";

// ─── Animated particle canvas ─────────────────────────────────────────────────
function ParticleCanvas() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    let animId;
    const particles = [];

    const resize = () => {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    for (let i = 0; i < 55; i++) {
      particles.push({
        x:     Math.random() * window.innerWidth,
        y:     Math.random() * window.innerHeight,
        r:     Math.random() * 1.8 + 0.3,
        alpha: Math.random() * 0.4 + 0.1,
        speed: Math.random() * 0.35 + 0.1,
        drift: (Math.random() - 0.5) * 0.3,
        hue:   Math.random() > 0.5 ? 38 : 210,
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => {
        p.y -= p.speed;
        p.x += p.drift;
        if (p.y < -10) { p.y = canvas.height + 10; p.x = Math.random() * canvas.width; }
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${p.hue}, 90%, 65%, ${p.alpha})`;
        ctx.fill();
      });
      animId = requestAnimationFrame(draw);
    };
    draw();

    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resize); };
  }, []);

  return <canvas id="particle-canvas" ref={canvasRef} />;
}

// ─── Processing step config ───────────────────────────────────────────────────
const STEPS = [
  { id: 'parse',   label: 'Reading quote with AI vision...' },
  { id: 'almm',    label: 'Checking ALMM panel compliance...' },
  { id: 'vendor',  label: 'Verifying vendor empanelment...' },
  { id: 'subsidy', label: 'Calculating PM Surya Ghar subsidy...' },
  { id: 'verdict', label: 'Building audit verdict...' },
];

// ─── App ──────────────────────────────────────────────────────────────────────
export default function App() {
  const [screen,         setScreen]         = useState('UPLOAD');
  const [verdictData,    setVerdictData]    = useState(null);
  const [isUploading,    setIsUploading]    = useState(false);
  const [dragActive,     setDragActive]     = useState(false);
  const [preview,        setPreview]        = useState(null);
  const [activeStep,     setActiveStep]     = useState(0);
  const [doneSteps,      setDoneSteps]      = useState([]);
  const [subsidyDisplay, setSubsidyDisplay] = useState(0);

  const fileInputRef    = useRef(null);
  const stepIntervalRef = useRef(null);

  // ── Animate processing steps ─────────────────────────────────
  useEffect(() => {
    if (screen !== 'PROCESSING') {
      clearInterval(stepIntervalRef.current);
      setActiveStep(0);
      setDoneSteps([]);
      return;
    }
    let idx = 0;
    stepIntervalRef.current = setInterval(() => {
      setDoneSteps(prev => [...prev, idx]);
      idx++;
      if (idx < STEPS.length) setActiveStep(idx);
      else clearInterval(stepIntervalRef.current);
    }, 3000);
    return () => clearInterval(stepIntervalRef.current);
  }, [screen]);

  // ── Count-up subsidy animation ────────────────────────────────
  useEffect(() => {
    if (screen !== 'VERDICT' || !verdictData?.subsidy_result?.eligible) return;
    const target = verdictData.subsidy_result.subsidy_amount || 0;
    let current = 0;
    const step = Math.ceil(target / 60);
    const timer = setInterval(() => {
      current = Math.min(current + step, target);
      setSubsidyDisplay(current);
      if (current >= target) clearInterval(timer);
    }, 22);
    return () => clearInterval(timer);
  }, [screen, verdictData]);

  // ── File handling ─────────────────────────────────────────────
  const processFile = useCallback(async (file) => {
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    try {
      setIsUploading(true);
      const compressed = await imageCompression(file, {
        maxSizeMB: 1, maxWidthOrHeight: 1920, useWebWorker: true,
      });
      const reader = new FileReader();
      reader.readAsDataURL(compressed);
      reader.onloadend = async () => {
        const base64data = reader.result.split(',')[1];
        setScreen('PROCESSING');
        setIsUploading(false);
        const resp = await fetch(`${API_URL}/audit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_b64: base64data, lang: 'hi' }),
        });
        const data = await resp.json();
        pollStatus(data.audit_id);
      };
    } catch (err) {
      console.error(err);
      alert('Error uploading. Please try again with a clearer image.');
      setScreen('UPLOAD');
      setIsUploading(false);
    }
  }, []);

  const handleFileInput = e => processFile(e.target.files?.[0]);

  const handleDrop = e => {
    e.preventDefault();
    setDragActive(false);
    processFile(e.dataTransfer.files?.[0]);
  };

  const pollStatus = auditId => {
    const interval = setInterval(async () => {
      try {
        const resp = await fetch(`${API_URL}/status/${auditId}`);
        const data = await resp.json();
        if (data.status === 'complete') {
          clearInterval(interval);
          setVerdictData(data);
          setScreen('VERDICT');
        } else if (data.status === 'failed') {
          clearInterval(interval);
          alert('Audit failed. Please try with a clearer image.');
          setScreen('UPLOAD');
        }
      } catch (err) { console.error(err); }
    }, 2000);
  };

  const reset = () => {
    setVerdictData(null);
    setPreview(null);
    setSubsidyDisplay(0);
    setScreen('UPLOAD');
  };

  const verdictClass =
    verdictData?.verdict?.verdict === 'GREEN' ? 'green'
    : verdictData?.verdict?.verdict === 'RED' ? 'red'
    : 'amber';

  // ─────────────────────────────────────────────────────────────
  return (
    <>
      <ParticleCanvas />
      <div className="hero-bg" />

      <section className="hero-section">

        {/* ── Hero copy (upload screen only) ────────────────── */}
        <AnimatePresence>
          {screen === 'UPLOAD' && (
            <motion.div
              key="hero-copy"
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16, transition: { duration: 0.25 } }}
              transition={{ duration: 0.5 }}
              style={{ textAlign: 'center', zIndex: 2, width: '100%' }}
            >
              <div className="brand-pill">
                <span className="brand-pill-dot" />
                PM Surya Ghar Audit Tool
              </div>

              <h1 className="hero-headline">
                Is Your Solar<br />
                <span className="line-gold">Quote Pakka?</span>
              </h1>

              <p className="hero-sub">
                Upload your vendor's quote — our AI checks ALMM compliance,
                subsidy eligibility &amp; price benchmarks in{' '}
                <strong>under 15 seconds</strong>.
              </p>

              <div className="stats-strip">
                <div className="stat-item">
                  <div className="stat-number">1 Cr+</div>
                  <div className="stat-label">Homes targeted</div>
                </div>
                <div className="stat-item">
                  <div className="stat-number">₹75,000 Cr</div>
                  <div className="stat-label">Scheme outlay</div>
                </div>
                <div className="stat-item">
                  <div className="stat-number">15 sec</div>
                  <div className="stat-label">Audit time</div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Main card ──────────────────────────────────────── */}
        <div className="audit-card">

          {/* Card header */}
          <div className="card-header">
            <div className="card-logo">☀️</div>
            <div className="card-logo-text">
              <h2>PakkaSolar</h2>
              <p>Smart Quote Auditor · MNRE Verified</p>
            </div>
          </div>

          <AnimatePresence mode="wait">

            {/* ─────────── SCREEN 1: UPLOAD ───────────────── */}
            {screen === 'UPLOAD' && (
              <motion.div
                key="upload"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -16 }}
                transition={{ duration: 0.32 }}
              >
                {preview && (
                  <img src={preview} alt="Quote preview" className="preview-thumb" />
                )}

                <div
                  id="upload-dropzone"
                  className={`upload-zone${dragActive ? ' drag-active' : ''}`}
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={e => { e.preventDefault(); setDragActive(true); }}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={handleDrop}
                >
                  <div className="upload-icon-wrap">
                    <UploadCloud size={30} />
                  </div>
                  <div className="upload-headline">
                    {dragActive ? 'Drop it here!' : 'Tap or drag your quote photo'}
                  </div>
                  <div className="upload-sub">
                    JPG, PNG or PDF of your solar installation quote<br />
                    <span>Supports Hindi &amp; English quotes</span>
                  </div>
                  <input
                    id="file-input"
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileInput}
                    accept="image/*"
                    style={{ display: 'none' }}
                  />
                </div>

                <button
                  id="scan-btn"
                  className="primary-btn"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading}
                >
                  {isUploading ? 'Compressing...' : (
                    <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                      Scan My Quote <ArrowRight size={18} />
                    </span>
                  )}
                </button>

                <div className="trust-strip">
                  <div className="trust-item"><Lock size={12} /> End-to-end encrypted</div>
                  <div className="trust-item"><ShieldCheck size={12} /> ALMM DB checked</div>
                  <div className="trust-item"><Zap size={12} /> Results in ~15s</div>
                </div>
              </motion.div>
            )}

            {/* ─────────── SCREEN 2: PROCESSING ───────────── */}
            {screen === 'PROCESSING' && (
              <motion.div
                key="processing"
                initial={{ opacity: 0, scale: 0.92 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 1.05 }}
                transition={{ duration: 0.38 }}
                className="processing-wrap"
              >
                <div className="solar-spinner">
                  <div className="solar-spinner-inner" />
                  <div className="solar-spinner-core" />
                </div>

                <div className="processing-title">AI is auditing your quote</div>
                <div className="processing-sub">Checking MNRE ALMM list &amp; vendor database</div>

                <ul className="check-steps">
                  {STEPS.map((step, i) => {
                    const isDone   = doneSteps.includes(i);
                    const isActive = activeStep === i && !isDone;
                    return (
                      <li
                        key={step.id}
                        className={`check-step${isDone ? ' done' : isActive ? ' active' : ''}`}
                      >
                        <span className={`step-icon ${isDone ? 'done' : isActive ? 'active' : 'pending'}`}>
                          {isDone ? '✓' : isActive ? '·' : ''}
                        </span>
                        {step.label}
                      </li>
                    );
                  })}
                </ul>
              </motion.div>
            )}

            {/* ─────────── SCREEN 3: VERDICT ──────────────── */}
            {screen === 'VERDICT' && verdictData && (
              <motion.div
                key="verdict"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.42 }}
              >
                {/* Coloured glow behind card */}
                <div className={`verdict-glow ${verdictClass}`} />

                {/* Verdict icon + label */}
                <div className="verdict-badge-wrap">
                  <motion.div
                    className={`verdict-icon-ring ${verdictClass}`}
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ delay: 0.12, type: 'spring', stiffness: 260, damping: 18 }}
                  >
                    {verdictClass === 'green' && <CheckCircle2 size={34} color="var(--success)" />}
                    {verdictClass === 'red'   && <XCircle      size={34} color="var(--danger)"  />}
                    {verdictClass === 'amber' && <AlertTriangle size={34} color="var(--warning)" />}
                  </motion.div>

                  <motion.div
                    className={`verdict-label ${verdictClass}`}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.28 }}
                  >
                    {verdictClass === 'green' ? '✅ All Clear'
                     : verdictClass === 'red' ? '🚨 High Risk'
                     : '⚠️ Needs Review'}
                  </motion.div>

                  <div className="verdict-sub">
                    {verdictData.extracted?.system_kw} kW · {verdictData.extracted?.brand}
                  </div>
                </div>

                {/* Audio */}
                {verdictData.verdict?.audio_url && (
                  <div className="audio-wrap">
                    <Volume2 size={16} color="var(--gold)" />
                    <span className="audio-label">AI Summary (Hindi)</span>
                    <audio controls className="audio-player" src={verdictData.verdict.audio_url} />
                  </div>
                )}

                {/* AI Summary */}
                <div className="summary-box">{verdictData.verdict?.summary_en}</div>

                {/* Subsidy */}
                {verdictData.subsidy_result?.eligible ? (
                  <motion.div
                    className="subsidy-card eligible"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.38 }}
                  >
                    <div className="subsidy-eyebrow">Estimated PM Surya Ghar Subsidy</div>
                    <div className="subsidy-amount">₹{subsidyDisplay.toLocaleString()}</div>
                    <div className="subsidy-breakdown">{verdictData.subsidy_result?.breakdown}</div>
                  </motion.div>
                ) : (
                  <div className="subsidy-card ineligible">
                    <h3 style={{ color: '#fca5a5', fontSize: '1rem', marginBottom: 6 }}>
                      Subsidy Eligibility Failed
                    </h3>
                    <p style={{ fontSize: '0.81rem', color: 'rgba(255,255,255,0.62)', fontFamily: 'DM Sans, sans-serif' }}>
                      {verdictData.subsidy_result?.note}
                    </p>
                  </div>
                )}

                {/* Check items */}
                <div className="checks-list">
                  <CheckCard title="ALMM Panel Check"     status={verdictData.almm_result?.dcr_status} detail={verdictData.almm_result?.detail}  icon={ShieldCheck} />
                  <CheckCard title="Vendor Empanelment"   status={verdictData.vendor_result?.status}   detail={verdictData.vendor_result?.detail}  icon={BadgeCheck}  />
                  <CheckCard title="Price Benchmark"      status={verdictData.price_result?.status}    detail={verdictData.price_result?.detail}   icon={Receipt}     />
                  <CheckCard
                    title="Estimated Generation"
                    status="INFO"
                    detail={`~${verdictData.gen_result?.annual_kwh} kWh/yr · saves ₹${verdictData.gen_result?.annual_savings_inr?.toLocaleString()}/yr`}
                    icon={Zap}
                  />
                </div>

                <button id="scan-another-btn" className="primary-btn" onClick={reset}>
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <RefreshCw size={16} /> Scan Another Quote
                  </span>
                </button>
              </motion.div>
            )}

          </AnimatePresence>
        </div>
      </section>
    </>
  );
}

// ─── CheckCard ────────────────────────────────────────────────────────────────
function CheckCard({ title, status, detail, icon: Icon }) {
  const s = (status || '').toUpperCase();
  let cls = 'info';
  if (s === 'PASS' || s === 'GREEN') cls = 'pass';
  else if (s === 'FAIL' || s === 'RED') cls = 'fail';
  else if (s === 'AMBER' || s === 'UNCERTAIN') cls = 'warn';

  const IconComp = cls === 'fail' ? XCircle : cls === 'warn' ? AlertTriangle : Icon;

  return (
    <motion.div
      className="check-item-card"
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.32 }}
    >
      <div className={`check-item-icon ${cls}`}>
        <IconComp size={18} />
      </div>
      <div className="check-content">
        <h4>{title}</h4>
        <p>{detail}</p>
      </div>
    </motion.div>
  );
}
