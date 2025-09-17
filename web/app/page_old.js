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
  
  // 대화 기능 상태
  const [chatMessage, setChatMessage] = useState("");
  const [chatResponse, setChatResponse] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  // 배포 환경에서 모바일 혼합 콘텐츠(https 페이지 -> http API) 차단 방지
  let API_BASE = process.env.NEXT_PUBLIC_API_BASE || "https://yt-summary-api-iu5d.onrender.com";
  if (typeof window !== "undefined") {
    const isHttpsPage = window.location?.protocol === "https:";
    if (isHttpsPage && API_BASE.startsWith("http://")) {
      API_BASE = API_BASE.replace(/^http:\/\//, "https://");
    }
    // 로컬 개발 환경 감지
    if (window.location?.hostname === "localhost" || window.location?.hostname === "127.0.0.1") {
      API_BASE = "http://127.0.0.1:8001";
    }
  }

  const simulateProgress = (isWhisper = false) => {
    const steps = isWhisper ? [
      { progress: 5, text: "영상 정보 확인 중...", method: "Whisper 시도 중" },
      { progress: 10, text: "Whisper로 전환...", method: "Whisper 오디오 다운로드" },
      { progress: 20, text: "오디오 다운로드 중...", method: "Whisper 오디오 다운로드" },
      { progress: 40, text: "오디오 전사 중...", method: "Whisper 오디오 전사" },
      { progress: 60, text: "전사 완료, AI 요약 생성 중...", method: "Whisper + AI 요약" },
      { progress: 80, text: "요약 정리 중...", method: "Whisper + AI 요약" },
      { progress: 95, text: "거의 완료...", method: "Whisper + AI 요약" },
    ] : [
      { progress: 10, text: "영상 정보 확인 중...", method: "Whisper" },
      { progress: 20, text: "오디오 다운로드 중...", method: "Whisper" },
      { progress: 30, text: "오디오 파일 준비 중...", method: "Whisper" },
      { progress: 40, text: "오디오에서 대본을 추출 중이에요! 🎵", method: "Whisper" },
      { progress: 50, text: "AI가 열심히 듣고 있어요... 👂", method: "Whisper" },
      { progress: 60, text: "대본 추출 거의 다 됐어요! ✨", method: "Whisper" },
      { progress: 70, text: "전사 완료! 이제 요약 만들고 있어요 📝", method: "Whisper + AI" },
      { progress: 80, text: "AI가 핵심만 뽑아내고 있어요 🧠", method: "Whisper + AI" },
      { progress: 90, text: "거의 다 됐어요! 조금만 기다려주세요 💫", method: "Whisper + AI" },
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
    
    try {
      setLoading(true);
      setProgress(0);
      setProgressText("요약을 시작합니다...");
      setMethod("Whisper");
      
      // 비디오 ID 추출
      const videoId = extractVideoId(url);
      if (!videoId) {
        throw new Error("유효한 유튜브 링크가 아닙니다.");
      }
      
      // WebSocket 연결로 실시간 진행률 받기
      const wsUrl = API_BASE.replace('http', 'ws') + `/ws/${videoId}`;
      const ws = new WebSocket(wsUrl);
      
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.error) {
          setError(`요약 오류: ${data.error}`);
          setLoading(false);
          return;
        }
        
        if (data.summary) {
          // 완료
          setProgress(100);
          setProgressText("완료! ✨");
          setMethod(data.method || "Whisper + AI");
          setSummary(data.summary);
          setLoading(false);
          ws.close();
          return;
        }
        
        // 진행률 업데이트
        setProgress(data.progress);
        setProgressText(data.text);
        setMethod(data.method);
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setError("연결 오류가 발생했습니다. 다시 시도해주세요.");
        setLoading(false);
      };
      
      ws.onclose = () => {
        if (loading) {
          setError("연결이 끊어졌습니다. 다시 시도해주세요.");
          setLoading(false);
        }
      };
      
    } catch (e) {
      setError(`요약 오류: ${e.message}`);
      setLoading(false);
    }
  };
  
  // 비디오 ID 추출 함수
  const extractVideoId = (url) => {
    const match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)/);
    return match ? match[1] : null;
  };
      
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
      let methodText = "Whisper + AI";
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

  const handleChat = async (e) => {
    e.preventDefault();
    if (!chatMessage.trim()) {
      setError("메시지를 입력해주세요");
      return;
    }

    setChatLoading(true);
    setError("");
    setChatResponse("");

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: chatMessage }),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "대화 중 오류가 발생했습니다");
      }

      const data = await res.json();
      setChatResponse(data.response);
      setChatMessage("");
    } catch (e) {
      setError(`대화 오류: ${e.message}`);
    } finally {
      setChatLoading(false);
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
        
        {/* 대화 기능 */}
        <div style={{ marginTop: 20, padding: 16, background: "rgba(255,255,255,0.04)", borderRadius: 12, border: "1px solid rgba(255,255,255,0.1)" }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: 16, color: "#fff" }}>OpenAI 연결 테스트</h3>
          <form onSubmit={handleChat} style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              placeholder="메시지를 입력하세요 (OpenAI 테스트용)"
              value={chatMessage}
              onChange={(e) => setChatMessage(e.target.value)}
              style={{ flex: 1, height: 40, borderRadius: 8, border: "1px solid rgba(255,255,255,0.22)", background:"rgba(10,20,50,0.35)", color:"#fff", padding:"0 12px" }}
            />
            <button type="submit" disabled={chatLoading} style={{ height: 40, borderRadius: 8, background: "#4CAF50", color: "#fff", padding: "0 16px", border: 0 }}>
              {chatLoading ? "대화 중..." : "대화"}
            </button>
          </form>
          {chatResponse && (
            <div style={{ marginTop: 12, padding: 12, background: "rgba(255,255,255,0.06)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.1)" }}>
              <div style={{ fontSize: 12, color: "rgba(255,255,255,0.6)", marginBottom: 4 }}>AI 응답:</div>
              <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{chatResponse}</div>
            </div>
          )}
        </div>
        
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
