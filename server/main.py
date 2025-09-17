from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import os
import time

from dotenv import load_dotenv
from openai import OpenAI
import httpx
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)
import youtube_transcript_api as yta
import yt_dlp
import tempfile
import shutil
import hashlib
import json

# .env 로드 (server 폴더 기준)
load_dotenv(dotenv_path=Path(__file__).parent / ".env", encoding="utf-8", override=True)

# 환경변수만 사용 (하드코딩 금지)

# 간단한 메모리 캐시 (실제 운영에서는 Redis 사용 권장)
CACHE = {}

def get_cache_key(video_id: str) -> str:
    """비디오 ID로 캐시 키 생성"""
    return f"video_{video_id}"

def get_cached_result(video_id: str) -> Optional[dict]:
    """캐시에서 결과 조회"""
    cache_key = get_cache_key(video_id)
    return CACHE.get(cache_key)

def set_cached_result(video_id: str, result: dict) -> None:
    """결과를 캐시에 저장"""
    cache_key = get_cache_key(video_id)
    CACHE[cache_key] = result
    # 메모리 사용량 제한 (최대 100개 항목)
    if len(CACHE) > 100:
        # 가장 오래된 항목 제거
        oldest_key = next(iter(CACHE))
        del CACHE[oldest_key]

app = FastAPI(title="yt-summary-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "YT Summary API"}


@app.get("/version")
def version():
    return {
        "commit": os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or None,
        "branch": os.getenv("RENDER_GIT_BRANCH") or os.getenv("GIT_BRANCH") or None,
        "youtube_transcript_api": getattr(yta, "__version__", None),
        "yt_dlp": getattr(yt_dlp, "__version__", None),
        "openai": os.getenv("OPENAI_API_KEY") is not None,
        "features": ["whisper_only"],
    }


class SummarizeRequest(BaseModel):
    url: str


class SummarizeResponse(BaseModel):
    language: Optional[str]
    summary: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


def extract_video_id(youtube_url: str) -> Optional[str]:
    try:
        parsed = urlparse(youtube_url)
        if parsed.netloc in {"www.youtube.com", "youtube.com", "m.youtube.com"}:
            qs = parse_qs(parsed.query)
            return qs.get("v", [None])[0]
        if parsed.netloc in {"youtu.be"}:
            return parsed.path.lstrip("/") or None
        return None
    except Exception:
        return None


def _apply_optional_proxy_from_env() -> None:
    proxy = os.getenv("YOUTUBE_PROXY")
    if proxy:
        os.environ.setdefault("HTTP_PROXY", proxy)
        os.environ.setdefault("HTTPS_PROXY", proxy)


def _with_backoff(callable_fn, *args, **kwargs):
    delays = [1, 3, 7, 12]
    last_err = None
    for delay in [0] + delays:
        if delay:
            time.sleep(delay)
        try:
            return callable_fn(*args, **kwargs)
        except Exception as e:
            msg = str(e)
            last_err = e
            print(f"백오프 중 오류 발생: {msg}")
            
            # 접근 제한 오류인 경우 즉시 실패
            if _is_access_restricted_error(msg):
                print(f"접근 제한 오류 감지, 백오프 중단: {msg}")
                raise e
            # 429 오류만 재시도
            if any(tok in msg for tok in ["Too Many Requests", "429", "sorry/index"]):
                print(f"429 오류, 재시도 예정: {msg}")
                continue
            print(f"기타 오류, 즉시 실패: {msg}")
            raise
    raise last_err


def _is_429_error(error_msg: str) -> bool:
    """429 오류인지 확인"""
    return any(tok in error_msg for tok in ["Too Many Requests", "429", "sorry/index"])


def _is_access_restricted_error(error_msg: str) -> bool:
    """접근 제한 관련 오류인지 확인"""
    restricted_keywords = [
        "Too Many Requests", "429", "sorry/index",
        "Sign in to confirm", "bot", "captcha", "verification",
        "blocked", "forbidden", "access denied", "rate limit",
        "quota exceeded", "daily limit", "hourly limit",
        "Client Error", "youtube", "transcript", "retrieve",
        "Could not retrieve", "transcript for the video",
        "YouTube 자막 접근 제한", "자막 처리 중 오류",
        "접근 제한", "제한", "restricted", "limit"
    ]
    error_lower = error_msg.lower()
    is_restricted = any(keyword.lower() in error_lower for keyword in restricted_keywords)
    if is_restricted:
        print(f"접근 제한 오류 감지: {error_msg}")
    return is_restricted


def _fallback_simple_transcript(video_id: str) -> str:
    """최후의 수단: 간단한 텍스트 반환"""
    return f"죄송합니다. 영상 ID {video_id}의 자막을 추출할 수 없습니다. YouTube의 봇 감지로 인해 일시적으로 접근이 제한되었습니다. 잠시 후 다시 시도해 주세요."


def _try_alternative_extraction(video_id: str) -> str:
    """대안적 추출 방법 시도"""
    try:
        # 방법 1: 다른 YouTube 도메인 시도
        alternative_urls = [
            f"https://m.youtube.com/watch?v={video_id}",
            f"https://youtu.be/{video_id}",
            f"https://www.youtube.com/embed/{video_id}",
        ]
        
        for url in alternative_urls:
            try:
                print(f"대안 URL 시도: {url}")
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
                    },
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info and info.get('title'):
                        return f"영상 제목: {info.get('title', '알 수 없음')}\n\n죄송합니다. 현재 YouTube의 봇 감지로 인해 자막 추출이 제한되고 있습니다. 영상 제목만 확인할 수 있었습니다. 잠시 후 다시 시도해 주세요."
            except Exception as e:
                print(f"대안 URL {url} 실패: {str(e)}")
                continue
                
        # 방법 2: 기본 메시지 반환
        return f"죄송합니다. 영상 ID {video_id}의 자막을 추출할 수 없습니다. YouTube의 봇 감지로 인해 일시적으로 접근이 제한되었습니다. 잠시 후 다시 시도해 주세요."
        
    except Exception as e:
        return f"죄송합니다. 영상 ID {video_id}의 자막을 추출할 수 없습니다. 오류: {str(e)}"


def get_video_duration(video_id: str) -> int:
    """영상 길이를 초 단위로 가져오기"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            },
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            url = f"https://www.youtube.com/watch?v={video_id}"
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration', 0)
            return int(duration) if duration else 0
    except Exception as e:
        print(f"영상 길이 가져오기 실패: {str(e)}")
        return 0

def _download_audio_with_ytdlp(video_id: str) -> str:
    """yt-dlp로 오디오 다운로드 후 Whisper로 전사 (YouTube API 완전 우회)"""
    temp_dir = tempfile.mkdtemp()
    try:
        print(f"🎬 Whisper 테스트: {video_id}")
        
        # 최적화된 yt-dlp 설정으로 시도
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio',  # M4A 우선 (더 빠름)
            'outtmpl': f'{temp_dir}/%(id)s.%(ext)s',
            'noplaylist': True,
            'quiet': True,
            'retries': 1,  # 재시도 최소화
            'fragment_retries': 1,  # 프래그먼트 재시도 최소화
            'socket_timeout': 30,  # 소켓 타임아웃 단축
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            },
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],  # DASH/HLS 스킵으로 더 빠른 다운로드
                }
            }
        }
        
        print(f"📥 yt-dlp 다운로드 시도: https://www.youtube.com/watch?v={video_id}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            url = f"https://www.youtube.com/watch?v={video_id}"
            try:
                ydl.download([url])
                print("✅ yt-dlp 다운로드 성공!")
            except Exception as e:
                error_msg = str(e)
                print(f"❌ yt-dlp 다운로드 실패: {error_msg}")
                
                # YouTube 접근 제한인지 확인
                if any(keyword in error_msg.lower() for keyword in [
                    'blocked', 'forbidden', 'access denied', 'rate limit', 
                    'quota exceeded', 'daily limit', 'hourly limit',
                    'client error', 'youtube', 'transcript', 'retrieve',
                    'could not retrieve', 'transcript for the video',
                    '접근 제한', '제한', 'restricted', 'limit', 'bot'
                ]):
                    raise Exception(f"YouTube 접근이 제한되었습니다. YouTube의 봇 감지로 인해 Whisper를 통한 오디오 다운로드가 차단되었습니다.")
                else:
                    raise Exception(f"오디오 다운로드 중 오류가 발생했습니다: {error_msg}")
        
        # 다운로드된 오디오 파일 찾기
        audio_files = [f for f in os.listdir(temp_dir) if f.endswith(('.wav', '.mp3', '.m4a', '.webm', '.ogg'))]
        if not audio_files:
            raise Exception("오디오 파일을 찾을 수 없습니다.")
        
        audio_path = os.path.join(temp_dir, audio_files[0])
        print(f"🎵 오디오 파일 다운로드 완료: {audio_files[0]}")
        
        # Whisper API로 전사
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        
        print("👂 Whisper로 오디오 전사 시작...")
        http_client = httpx.Client(trust_env=False, timeout=120, follow_redirects=True)
        client = OpenAI(api_key=api_key, http_client=http_client)
        
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
                temperature=0.0,  # 일관성 있는 결과를 위해 온도 0
                language="ko"  # 한국어 우선 처리
            )
        
        print("✨ Whisper 전사 완료!")
        return transcript.strip()
        
    except Exception as e:
        print(f"Whisper 처리 중 오류: {str(e)}")
        raise
    finally:
        # 임시 파일 정리
        shutil.rmtree(temp_dir, ignore_errors=True)


def fetch_transcript_text(video_id: str) -> tuple[str, Optional[str]]:
    """Whisper로 자막 추출"""
    try:
        print(f"🎵 Whisper로 자막 추출 시작: {video_id}")
        whisper_text = _download_audio_with_ytdlp(video_id)
        print("✨ Whisper로 자막 추출 완료!")
        return whisper_text, "whisper"  # Whisper는 언어 자동 감지
        
    except Exception as e:
        error_msg = str(e)
        print(f"Whisper 전사 중 오류 발생: {error_msg}")
        
        # 접근 제한 오류인지 확인
        if _is_access_restricted_error(error_msg):
            print(f"Whisper에서 접근 제한 감지: {error_msg}")
            raise Exception(f"YouTube 접근이 제한되었습니다. YouTube의 봇 감지로 인해 Whisper를 통한 오디오 전사가 차단되었습니다. 잠시 후 다시 시도해 주세요.")
        else:
            # 기타 오류는 그대로 전파
            print(f"Whisper 전사 실패 (기타 오류): {error_msg}")
            raise Exception(f"오디오 전사 중 오류가 발생했습니다: {error_msg}")


def summarize_with_openai(transcript_text: str, lang_code: Optional[str]) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    # 시스템/환경 프록시를 무시하도록 httpx 클라이언트를 명시적으로 주입
    http_client = httpx.Client(trust_env=False, timeout=60, follow_redirects=True)
    client = OpenAI(api_key=api_key, http_client=http_client)

    # 입력 길이 방어
    max_chars = 16000
    if len(transcript_text) > max_chars:
        head = transcript_text[:12000]
        tail = transcript_text[-3000:]
        transcript_text = head + "\n...\n" + tail

    system_prompt = (
        "당신은 유튜브 영상 자막을 한국어로 구조화해 주는 비즈니스 전문가입니다. "
        "간결하고 객관적인 정보 중심 문체를 사용하고, 번역투를 피하며 과도한 구어체는 지양하세요. "
        "불필요한 장식(굵게, 태그 등)은 쓰지 말고 핵심만 담습니다. "
        "각 섹션 사이에는 빈 줄 한 줄을 넣어 가독성을 높이세요.\n\n"
        "형식:\n"
        "1) 제목: <영상 주제 한 줄>\n\n"
        "2) 핵심 주제: <이 영상을 관통하는 한 줄 핵심>\n\n"
        "3) 내용:\n   - <2~3개의 짧은 단락으로, 문장 사이가 자연스럽게 이어지도록 연결어를 활용해 설명>\n   - <콘텐츠에 '세 가지/N가지 방법·접근·전략'이 등장하면, 각 항목을 간단 설명과 함께 소개>\n\n"
        "4) 핵심 인사이트:\n   - <불릿 5~8개, 실행/판단에 도움이 되는 포인트>\n\n"
        "5) 3줄 요약:\n   1) <핵심 한 문장>\n   2) <핵심 한 문장>\n   3) <핵심 한 문장>\n"
    )

    if lang_code == "ko":
        user_prompt = (
            "다음 자막을 위 형식에 맞춰 한국어로 구조화 요약해 주세요.\n\n"
            f"자막:\n{transcript_text}"
        )
    else:
        user_prompt = (
            "다음 자막이 영어이거나 혼합어일 수 있습니다. 내용을 한국어로 자연스럽게 번역한 뒤, "
            "위 형식에 맞춰 구조화 요약해 주세요.\n\n"
            f"자막:\n{transcript_text}"
        )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )

    return completion.choices[0].message.content.strip()


@app.post("/summarize", response_model=SummarizeResponse)
def summarize(req: SummarizeRequest):
    video_id = extract_video_id(req.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="유효한 유튜브 링크가 아닙니다.")
    try:
        text, lang_code = fetch_transcript_text(video_id)
    except (TranscriptsDisabled, NoTranscriptFound):
        raise HTTPException(status_code=404, detail="해당 영상에서 자막을 찾을 수 없습니다.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"자막 처리 중 오류: {str(e)}")

    try:
        summary = summarize_with_openai(text, lang_code)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요약 중 오류: {str(e)}")

    return SummarizeResponse(language=lang_code, summary=summary)


@app.post("/summarize/{video_id}")
def summarize_by_id(video_id: str):
    """비디오 ID로 직접 요약하는 엔드포인트 (WebSocket 없이)"""
    # 캐시에서 결과 확인
    cached_result = get_cached_result(video_id)
    if cached_result:
        print(f"🚀 캐시에서 결과 반환: {video_id}")
        return cached_result
    
    # 영상 길이 가져오기
    duration = get_video_duration(video_id)
    estimated_time = estimate_processing_time(duration)
    
    try:
        text, lang_code = fetch_transcript_text(video_id)
    except (TranscriptsDisabled, NoTranscriptFound):
        raise HTTPException(status_code=404, detail="해당 영상에서 자막을 찾을 수 없습니다.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"자막 처리 중 오류: {str(e)}")

    try:
        summary = summarize_with_openai(text, lang_code)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요약 중 오류: {str(e)}")

    result = {
        "summary": summary,
        "language": lang_code,
        "method": "Whisper + AI",
        "duration": duration,
        "estimated_time": estimated_time
    }
    
    # 결과를 캐시에 저장
    set_cached_result(video_id, result)
    print(f"💾 결과를 캐시에 저장: {video_id}")
    
    return result

def estimate_processing_time(duration_seconds: int) -> int:
    """영상 길이에 따른 예상 처리 시간 계산 (초 단위)"""
    if duration_seconds == 0:
        return 60  # 기본값 1분
    
    # 15분 영상 = 70초, 5분 영상 = 48초 기준으로 선형 보간
    # 15분(900초) -> 70초, 5분(300초) -> 48초
    # y = ax + b 형태로 계산
    x1, y1 = 300, 48   # 5분 -> 48초
    x2, y2 = 900, 70   # 15분 -> 70초
    
    if duration_seconds <= x1:
        # 5분 이하: 48초 고정
        return 48
    elif duration_seconds >= x2:
        # 15분 이상: 70초 고정
        return 70
    else:
        # 5분~15분 사이: 선형 보간
        a = (y2 - y1) / (x2 - x1)
        b = y1 - a * x1
        estimated = a * duration_seconds + b
        return int(estimated)




@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

        http_client = httpx.Client(trust_env=False, timeout=60, follow_redirects=True)
        client = OpenAI(api_key=api_key, http_client=http_client)

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 도움이 되는 AI 어시스턴트입니다. 한국어로 친절하고 정확하게 답변해주세요."},
                {"role": "user", "content": req.message},
            ],
            temperature=0.7,
        )

        response = completion.choices[0].message.content.strip()
        return ChatResponse(response=response)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"대화 중 오류: {str(e)}")

