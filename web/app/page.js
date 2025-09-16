"use client";
import { useState } from "react";

export default function Home() {
  const [url, setUrl] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSummary("");
    if (!url || url.length < 10) {
      setError("유효한 유튜브 링크를 입력해 주세요");
      return;
    }
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `서버 오류 (${res.status})`);
      }
      const data = await res.json();
      setSummary(data.summary || "요약 결과가 없습니다.");
    } catch (e) {
      setError(e.message || "요청 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    try {
      if (!summary) return;
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(summary);
        alert("복사되었습니다.");
      } else {
        const t = document.createElement("textarea");
        t.value = summary;
        document.body.appendChild(t);
        t.select();
        document.execCommand("copy");
        document.body.removeChild(t);
        alert("복사되었습니다.");
      }
    } catch {
      alert("복사에 실패했습니다.");
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "linear-gradient(135deg,#0B1437,#2C3E8F)",
      padding: 24,
    }}>
      <div style={{
        width: "100%",
        maxWidth: 720,
        background: "rgba(255,255,255,0.08)",
        border: "1px solid rgba(255,255,255,0.18)",
        borderRadius: 16,
        padding: 24,
        color: "#fff",
      }}>
        <h1 style={{ margin: 0, marginBottom: 16 }}>유튜브 영상 요약</h1>
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
          <input
            type="url"
            placeholder="유튜브 링크를 입력하세요"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            style={{ flex: 1, height: 44, borderRadius: 10, border: "1px solid rgba(255,255,255,0.22)", background:"rgba(10,20,50,0.35)", color:"#fff", padding:"0 12px" }}
          />
          <button type="submit" disabled={loading} style={{ height: 44, borderRadius: 10, background: "#6A7DFF", color: "#fff", padding: "0 16px", border: 0 }}>
            {loading ? "요약 중..." : "요약하기"}
          </button>
        </form>
        {error && (
          <div style={{ marginTop: 12, color: "#FF9E9E" }}>{error}</div>
        )}
        {summary && (
          <div style={{ marginTop: 20, background:"rgba(255,255,255,0.06)", border:"1px solid rgba(255,255,255,0.18)", borderRadius: 12, padding: 16 }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>요약 결과</div>
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{summary}</div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
              <button onClick={handleCopy} style={{ height: 32, padding: "0 10px", borderRadius: 8, border:"1px solid rgba(255,255,255,0.22)", background:"rgba(255,255,255,0.12)", color:"#fff" }}>복사하기</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
