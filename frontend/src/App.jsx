import React, { useState, useRef } from 'react';
import { UploadCloud, CheckCircle2, XCircle, AlertTriangle, ShieldCheck, Zap, Receipt, Volume2 } from 'lucide-react';
import imageCompression from 'browser-image-compression';
import { motion, AnimatePresence } from 'framer-motion';
import './index.css';

const API_URL = "https://7a8zj1nbya.execute-api.ap-south-1.amazonaws.com/prod";

export default function App() {
  const [screen, setScreen] = useState('UPLOAD'); // UPLOAD, PROCESSING, VERDICT
  const [verdictData, setVerdictData] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  
  const fileInputRef = useRef(null);

  const handleUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      setIsUploading(true);
      
      // 1. Compress Image (keeps upload super fast on 3G)
      const options = {
        maxSizeMB: 1,
        maxWidthOrHeight: 1920,
        useWebWorker: true
      };
      const compressedFile = await imageCompression(file, options);
      
      // 2. Base64 Encode
      const reader = new FileReader();
      reader.readAsDataURL(compressedFile);
      reader.onloadend = async () => {
        const base64data = reader.result.split(',')[1];
        
        // 3. Send to API
        setScreen('PROCESSING');
        const resp = await fetch(`${API_URL}/audit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_b64: base64data, lang: 'hi' }) // or 'en'
        });
        
        const data = await resp.json();
        pollStatus(data.audit_id);
      };
    } catch (error) {
      console.error(error);
      alert("Error uploading image");
      setScreen('UPLOAD');
    } finally {
      setIsUploading(false);
    }
  };

  const pollStatus = async (auditId) => {
    const interval = setInterval(async () => {
      const resp = await fetch(`${API_URL}/status/${auditId}`);
      const data = await resp.json();
      
      if (data.status === 'complete') {
        clearInterval(interval);
        setVerdictData(data);
        setScreen('VERDICT');
      } else if (data.status === 'failed') {
        clearInterval(interval);
        alert("Audit failed! Please try again with a clearer image.");
        setScreen('UPLOAD');
      }
    }, 2000);
  };

  return (
    <div className="glass-card">
      <div className="header">
        <h1>PakkaSolar</h1>
        <p>Smart PM Surya Ghar Quote Audit</p>
      </div>

      <AnimatePresence mode="wait">
        
        {/* SCREEN 1: UPLOAD */}
        {screen === 'UPLOAD' && (
          <motion.div
            key="upload"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            <div 
              className="upload-area"
              onClick={() => fileInputRef.current?.click()}
            >
              <UploadCloud size={48} className="upload-icon" />
              <h3>Tap to upload photo</h3>
              <p style={{ marginTop: '8px', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                of your solar quote document
              </p>
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleUpload} 
                accept="image/*" 
                style={{ display: 'none' }} 
              />
            </div>
            <button className="primary-btn" onClick={() => fileInputRef.current?.click()}>
              {isUploading ? 'Compressing...' : 'Scan My Quote'}
            </button>
          </motion.div>
        )}

        {/* SCREEN 2: PROCESSING */}
        {screen === 'PROCESSING' && (
          <motion.div
            key="processing"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.1 }}
            style={{ textAlign: 'center', padding: '40px 0' }}
          >
            <div className="spinner"></div>
            <h3 style={{ marginBottom: '8px' }}>AI is analyzing your quote...</h3>
            <p style={{ color: 'var(--text-secondary)' }}>Checking MNRE ALMM List & Vendor DB</p>
          </motion.div>
        )}

        {/* SCREEN 3: VERDICT */}
        {screen === 'VERDICT' && verdictData && (
          <motion.div
            key="verdict"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="verdict-header">
              <div className={`verdict-badge verdict-${verdictData.verdict.verdict}`}>
                {verdictData.verdict.verdict === 'GREEN' ? 'ALL CLEAR' : 
                 verdictData.verdict.verdict === 'RED' ? 'HIGH RISK' : 'WARNING'}
              </div>
              <div>
                <h3 style={{ fontSize: '1.2rem', marginBottom: '4px' }}>Audit Complete</h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                  {verdictData.extracted.system_kw} kW System • {verdictData.extracted.brand}
                </p>
              </div>
            </div>

            {/* Audio Player */}
            {verdictData.verdict.audio_url && (
              <div style={{ marginBottom: '24px' }}>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Volume2 size={16} /> Listen to AI Summary (Hindi)
                </p>
                <audio controls className="audio-player" src={verdictData.verdict.audio_url}></audio>
              </div>
            )}

            <div className="summary-box">
              {verdictData.verdict.summary_en}
            </div>

            {/* Subsidy Highlight */}
            {verdictData.subsidy_result.eligible ? (
              <div className="subsidy-card">
                <p style={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.8)' }}>Estimated PM Surya Ghar Subsidy</p>
                <div className="subsidy-amount">₹{verdictData.subsidy_result.subsidy_amount.toLocaleString()}</div>
                <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)' }}>{verdictData.subsidy_result.breakdown}</p>
              </div>
            ) : (
              <div className="subsidy-card" style={{ background: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
                <h3 style={{ color: '#fca5a5' }}>Subsidy Eligibility Failed</h3>
                <p style={{ fontSize: '0.85rem', marginTop: '8px', color: 'rgba(255,255,255,0.7)' }}>{verdictData.subsidy_result.note}</p>
              </div>
            )}

            {/* Detailed Checks */}
            <div className="checks-list">
              <CheckItem 
                title="ALMM Panel Check" 
                status={verdictData.almm_result.dcr_status} 
                detail={verdictData.almm_result.detail} 
                icon={ShieldCheck} 
              />
              <CheckItem 
                title="Vendor Empanelment" 
                status={verdictData.vendor_result.status} 
                detail={verdictData.vendor_result.detail} 
                icon={CheckCircle2} 
              />
              <CheckItem 
                title="Price Benchmark" 
                status={verdictData.price_result.status} 
                detail={verdictData.price_result.detail} 
                icon={Receipt} 
              />
              <CheckItem 
                title="Estimated Generation" 
                status="INFO" 
                detail={`~${verdictData.gen_result.annual_kwh} kWh/year saving ₹${verdictData.gen_result.annual_savings_inr.toLocaleString()}`} 
                icon={Zap} 
              />
            </div>

            <button className="primary-btn" onClick={() => { setVerdictData(null); setScreen('UPLOAD'); }}>
              Scan Another Quote
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function CheckItem({ title, status, detail, icon: Icon }) {
  let color = 'var(--text-secondary)';
  if (status === 'PASS' || status === 'GREEN') color = 'var(--success)';
  if (status === 'FAIL' || status === 'RED') color = 'var(--danger)';
  if (status === 'AMBER' || status === 'UNCERTAIN') color = 'var(--warning)';
  if (status === 'INFO') color = 'var(--accent-blue)';

  return (
    <div className="check-item">
      <div className="check-icon" style={{ color }}>
        {status === 'FAIL' ? <XCircle size={20} /> : 
         status === 'AMBER' ? <AlertTriangle size={20} /> : <Icon size={20} />}
      </div>
      <div className="check-content">
        <h4>{title}</h4>
        <p>{detail}</p>
      </div>
    </div>
  );
}
