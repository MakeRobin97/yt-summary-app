"use client";
import { useState } from "react";

export default function Home() {
  const [url, setUrl] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState("");
  const [method, setMethod] = useState("");

  // 배포 환경에서 모바일 혼합 콘텐츠(https 페이지 -> http API) 차단 방지
  let API_BASE = process.env.NEXT_PUBLIC_API_BASE || "https://yt-summary-api-iu5d.onrender.com";
  if (typeof window !== "undefined") {
    const isHttpsPage = window.location?.protocol === "https:";
    if (isHttpsPage && API_BASE.startsWith("http://")) {
      API_BASE = API_BASE.replace(/^http:\/\//, "https://");
    }
  }

  const simulateProgress = (isWhisper = false) => {
    const steps = isWhisper ? [
      { progress: 5, text: "영상 정보 확인 중...", method: "YouTube API 시도 중" },
      { progress: 10, text: "YouTube API 실패, Whisper로 전환...", method: "Whisper 오디오 다운로드" },
      { progress: 20, text: "오디오 다운로드 중...", method: "Whisper 오디오 다운로드" },
      { progress: 40, text: "오디오 전사 중...", method: "Whisper 오디오 전사" },
      { progress: 60, text: "전사 완료, AI 요약 생성 중...", method: "Whisper + AI 요약" },
      { progress: 80, text: "요약 정리 중...", method: "Whisper + AI 요약" },
      { progress: 95, text: "거의 완료...", method: "Whisper + AI 요약" },
    ] : [
      { progress: 10, text: "영상 정보 확인 중...", method: "YouTube API" },
      { progress: 25, text: "자막 추출 중...", method: "YouTube API" },
      { progress: 50, text: "자막 분석 중...", method: "YouTube API" },
      { progress: 75, text: "AI 요약 생성 중...", method: "YouTube API + AI" },
      { progress: 90, text: "최종 정리 중...", method: "YouTube API + AI" },
    ];
    
    let currentStep = 0;
    const interval = setInterval(() => {
      if (currentStep < steps.length) {
        setProgress(steps[currentStep].progress);
        setProgressText(steps[currentStep].text);
        setMethod(steps[currentStep].method);
        currentStep++;
      } else {
        clearInterval(interval);
      }
    }, isWhisper ? 2000 : 1000); // Whisper는 더 오래 걸리므로 2초 간격
    
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
      setMethod("YouTube API");
      
      // 진행 상황 시뮬레이션 시작 (기본적으로 YouTube API)
      progressInterval = simulateProgress(false);
      
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
      
      // 응답에서 사용된 방법 확인 (서버에서 language 필드로 구분)
      const isWhisperUsed = data.language === "whisper";
      const isAlternativeUsed = data.language === "alternative";
      const isFallbackUsed = data.language === "fallback";
      
      if (isWhisperUsed) {
        // Whisper 사용된 경우 프로그레스 조정
        clearInterval(progressInterval);
        progressInterval = simulateProgress(true);
        
        // Whisper 프로그레스가 완료될 때까지 대기
        await new Promise(resolve => setTimeout(resolve, 8000));
      }
      
      setProgress(100);
      setProgressText("완료!");
      
      // 사용된 방법에 따라 메서드 표시
      let methodText = "YouTube API + AI";
      if (isWhisperUsed) methodText = "Whisper + AI";
      else if (isAlternativeUsed) methodText = "대안적 추출 + AI";
      else if (isFallbackUsed) methodText = "기본 메시지";
      
      setMethod(methodText);
      setSummary(data.summary || "요약 결과가 없습니다.");
    } catch (e) {
      // 오류 발생 시 즉시 프로그레스 바 중단
      if (progressInterval) {
        clearInterval(progressInterval);
      }
      setProgress(0);
      setProgressText("");
      setMethod("");
      
      // 오류 메시지 개선
      let errorMessage = e.message || "요청 중 오류가 발생했습니다.";
      if (errorMessage.includes("봇 감지") || errorMessage.includes("접근 제한") || errorMessage.includes("모두 접근이 제한")) {
        errorMessage = "🚫 YouTube 접근이 제한되었습니다. 잠시 후 다시 시도해 주세요.";
      } else if (errorMessage.includes("자막을 찾을 수 없습니다")) {
        errorMessage = "📝 해당 영상에는 자막이 없습니다. 자막이 있는 영상을 시도해 주세요.";
      } else if (errorMessage.includes("서버 오류")) {
        errorMessage = "🔧 서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.";
      } else if (errorMessage.includes("Whisper를 시도했지만 실패")) {
        errorMessage = "⚠️ YouTube 접근 제한으로 대안 방법도 실패했습니다. 잠시 후 다시 시도해 주세요.";
      }
      
      setError(errorMessage);
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
            {loading ? "요약 중..." : "요약"}
          </button>
        </form>
        {error && (
          <div style={{ marginTop: 12, color: "#FF9E9E" }}>{error}</div>
        )}
        {loading && progress > 0 && (
          <div style={{ marginTop: 20, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.18)", borderRadius: 12, padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <div>
                <span style={{ fontSize: 14, fontWeight: 500 }}>{progressText}</span>
                {method && (
                  <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginTop: 2 }}>
                    사용 방법: {method}
                  </div>
                )}
              </div>
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
                background: method?.includes("Whisper") 
                  ? "linear-gradient(90deg, #FF6B6B, #FF8E53)" 
                  : method?.includes("대안적") || method?.includes("기본")
                  ? "linear-gradient(90deg, #FFA726, #FF7043)"
                  : "linear-gradient(90deg, #6A7DFF, #9B59B6)", 
                borderRadius: 3,
                transition: "width 0.3s ease-in-out"
              }} />
            </div>
            {method?.includes("Whisper") && (
              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)", marginTop: 8, textAlign: "center" }}>
                💡 Whisper 사용 시 오디오 다운로드로 인해 시간이 더 걸릴 수 있습니다
              </div>
            )}
            {(method?.includes("대안적") || method?.includes("기본")) && (
              <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)", marginTop: 8, textAlign: "center" }}>
                ⚠️ YouTube 접근 제한으로 인해 제한된 정보만 제공됩니다
              </div>
            )}
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
