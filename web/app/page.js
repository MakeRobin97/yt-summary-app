"use client";
import { useState } from "react";

export default function Home() {
  const [url, setUrl] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState("");

  // 배포 환경에서 모바일 혼합 콘텐츠(https 페이지 -> http API) 차단 방지
  let API_BASE = process.env.NEXT_PUBLIC_API_BASE || "https://yt-summary-api-iu5d.onrender.com";
  if (typeof window !== "undefined") {
    const isHttpsPage = window.location?.protocol === "https:";
    if (isHttpsPage && API_BASE.startsWith("http://")) {
      API_BASE = API_BASE.replace(/^http:\/\//, "https://");
    }
  }

  const simulateProgress = () => {
    const steps = [
      { progress: 10, text: "영상 정보 확인 중..." },
      { progress: 25, text: "자막 추출 중..." },
      { progress: 50, text: "자막 분석 중..." },
      { progress: 75, text: "AI 요약 생성 중..." },
      { progress: 90, text: "최종 정리 중..." },
    ];
    
    let currentStep = 0;
    const interval = setInterval(() => {
      if (currentStep < steps.length) {
        setProgress(steps[currentStep].progress);
        setProgressText(steps[currentStep].text);
        currentStep++;
      } else {
        clearInterval(interval);
      }
    }, 1000);
    
    return interval;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSummary("");
    if (!url || url.length < 10) {
      setError("유효한 유튜브 링크를 입력해 주세요");
      return;
    }
    
    let progressInterval;
    try {
      setLoading(true);
      setProgress(0);
      setProgressText("요약을 시작합니다...");
      
      // 진행 상황 시뮬레이션 시작
      progressInterval = simulateProgress();
      
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
      setProgress(100);
      setProgressText("완료!");
      setSummary(data.summary || "요약 결과가 없습니다.");
    } catch (e) {
      setError(e.message || "요청 중 오류가 발생했습니다.");
    } finally {
      if (progressInterval) {
        clearInterval(progressInterval);
      }
      setLoading(false);
      // 완료 후 1초 뒤 진행바 숨김
      setTimeout(() => {
        setProgress(0);
        setProgressText("");
      }, 1000);
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
            {loading ? "요약 중..." : "요약"}
          </button>
        </form>
        {error && (
          <div style={{ marginTop: 12, color: "#FF9E9E" }}>{error}</div>
        )}
        {loading && progress > 0 && (
          <div style={{ marginTop: 20, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.18)", borderRadius: 12, padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 500 }}>{progressText}</span>
              <span style={{ fontSize: 12, color: "rgba(255,255,255,0.7)" }}>{progress}%</span>
            </div>
            <div style={{ 
              width: "100%", 
              height: 6, 
              background: "rgba(255,255,255,0.1)", 
              borderRadius: 3, 
              overflow: "hidden" 
            }}>
              <div style={{ 
                width: `${progress}%`, 
                height: "100%", 
                background: "linear-gradient(90deg, #6A7DFF, #9B59B6)", 
                borderRadius: 3,
                transition: "width 0.3s ease-in-out"
              }} />
            </div>
          </div>
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
