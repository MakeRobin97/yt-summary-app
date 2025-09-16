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

# .env 로드 (server 폴더 기준)
load_dotenv(dotenv_path=Path(__file__).parent / ".env", encoding="utf-8", override=True)

# 환경변수만 사용 (하드코딩 금지)


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
        "features": ["youtube_api", "whisper_fallback"],
    }


class SummarizeRequest(BaseModel):
    url: str


class SummarizeResponse(BaseModel):
    language: Optional[str]
    summary: str


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


def _download_audio_with_ytdlp(video_id: str) -> str:
    """yt-dlp로 오디오 다운로드 후 Whisper로 전사 (다중 시도)"""
    temp_dir = tempfile.mkdtemp()
    try:
        # 여러 시도 방법
        strategies = [
            # 전략 1: 쿠키 기반 인증 + 강화된 우회
            {
                'format': 'bestaudio/best',
                'outtmpl': f'{temp_dir}/%(id)s.%(ext)s',
                'extractaudio': True,
                'audioformat': 'wav',
                'noplaylist': True,
                'quiet': True,
                'extractor_retries': 5,
                'retries': 5,
                'sleep_interval': 3,
                'max_sleep_interval': 15,
                'cookiesfrombrowser': ['chrome', 'firefox', 'safari', 'edge'],
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                },
                'geo_bypass': True,
                'geo_bypass_country': 'US',
                'no_check_certificate': True,
            },
            # 전략 2: 강화된 우회 설정
            {
                'format': 'bestaudio/best',
                'outtmpl': f'{temp_dir}/%(id)s.%(ext)s',
                'extractaudio': True,
                'audioformat': 'wav',
                'noplaylist': True,
                'quiet': True,
                'extractor_retries': 5,
                'fragment_retries': 5,
                'retries': 5,
                'sleep_interval': 2,
                'max_sleep_interval': 10,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
                'geo_bypass': True,
                'geo_bypass_country': 'US',
                'no_check_certificate': True,
            },
            # 전략 3: 모바일 User-Agent
            {
                'format': 'bestaudio/best',
                'outtmpl': f'{temp_dir}/%(id)s.%(ext)s',
                'extractaudio': True,
                'audioformat': 'wav',
                'noplaylist': True,
                'quiet': True,
                'retries': 3,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                },
            },
            # 전략 4: 최소 설정
            {
                'format': 'worstaudio/worst',
                'outtmpl': f'{temp_dir}/%(id)s.%(ext)s',
                'noplaylist': True,
                'quiet': True,
                'retries': 1,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
                },
            }
        ]
        
        last_error = None
        for i, ydl_opts in enumerate(strategies):
            try:
                print(f"yt-dlp 시도 {i+1}/{len(strategies)}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    ydl.download([url])
                
                # 다운로드된 오디오 파일 찾기
                audio_files = [f for f in os.listdir(temp_dir) if f.endswith(('.wav', '.mp3', '.m4a', '.webm', '.ogg'))]
                if audio_files:
                    print(f"yt-dlp 시도 {i+1} 성공!")
                    break
                else:
                    raise Exception("오디오 파일을 찾을 수 없습니다.")
                    
            except Exception as e:
                last_error = e
                print(f"yt-dlp 시도 {i+1} 실패: {str(e)}")
                
                # 접근 제한 오류인 경우 즉시 실패
                if _is_access_restricted_error(str(e)):
                    print("접근 제한 오류로 인해 즉시 실패")
                    raise Exception(f"YouTube 접근 제한으로 인해 오디오 다운로드가 차단되었습니다: {str(e)}")
                
                if i < len(strategies) - 1:
                    time.sleep(3)  # 다음 시도 전 대기
                    continue
                else:
                    # 모든 전략 실패 시 즉시 실패
                    print("모든 yt-dlp 전략 실패")
                    raise Exception(f"모든 다운로드 시도 실패. 마지막 오류: {str(last_error)}")
        
        # 다운로드된 오디오 파일 찾기
        audio_files = [f for f in os.listdir(temp_dir) if f.endswith(('.wav', '.mp3', '.m4a', '.webm', '.ogg'))]
        if not audio_files:
            raise Exception(f"모든 시도 실패. 마지막 오류: {str(last_error)}")
        
        audio_path = os.path.join(temp_dir, audio_files[0])
        
        # Whisper API로 전사
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        
        http_client = httpx.Client(trust_env=False, timeout=120, follow_redirects=True)
        client = OpenAI(api_key=api_key, http_client=http_client)
        
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        
        return transcript.strip()
        
    finally:
        # 임시 파일 정리
        shutil.rmtree(temp_dir, ignore_errors=True)


def fetch_transcript_text(video_id: str) -> tuple[str, Optional[str]]:
    """YouTube API로 자막 추출 시도, 접근 제한 시 Whisper로 폴백"""
    try:
        # 1단계: YouTube API로 자막 추출 시도
        _apply_optional_proxy_from_env()
        transcript_list = _with_backoff(YouTubeTranscriptApi.list_transcripts, video_id)
        lang_code: Optional[str] = None
        transcript = None

        # 우선순위: 한국어 -> 영어
        for target in ["ko", "en"]:
            try:
                transcript = transcript_list.find_manually_created_transcript([target])
                lang_code = target
                break
            except Exception as e:
                # 접근 제한 오류인 경우 즉시 실패
                if _is_access_restricted_error(str(e)):
                    print(f"자막 검색 중 접근 제한 감지: {str(e)}")
                    raise e
                try:
                    transcript = transcript_list.find_transcript([target])
                    lang_code = target
                    break
                except Exception as e2:
                    # 접근 제한 오류인 경우 즉시 실패
                    if _is_access_restricted_error(str(e2)):
                        print(f"자막 검색 중 접근 제한 감지: {str(e2)}")
                        raise e2
                    continue

        if transcript is None:
            # 자동 번역으로 한국어 우선 시도, 실패 시 영어 자동 생성본
            try:
                transcript = transcript_list.find_transcript(["en"]).translate("ko")
                lang_code = "ko"
            except Exception as e:
                # 접근 제한 오류인 경우 즉시 실패
                if _is_access_restricted_error(str(e)):
                    print(f"자막 번역 중 접근 제한 감지: {str(e)}")
                    raise e
                try:
                    transcript = transcript_list.find_transcript(["en"])
                    lang_code = "en"
                except Exception as e2:
                    # 접근 제한 오류인 경우 즉시 실패
                    if _is_access_restricted_error(str(e2)):
                        print(f"자막 검색 중 접근 제한 감지: {str(e2)}")
                        raise e2
                    raise NoTranscriptFound(video_id)

        chunks = _with_backoff(transcript.fetch)
        texts: list[str] = []
        for part in chunks:
            t = getattr(part, "text", None)
            if t is None and isinstance(part, dict):
                t = part.get("text")
            if t:
                texts.append(t)
        text = " ".join(texts)
        if not text:
            raise NoTranscriptFound(video_id)
        return text, lang_code
        
    except Exception as e:
        error_msg = str(e)
        print(f"fetch_transcript_text에서 오류 발생: {error_msg}")
        
        # 2단계: 접근 제한 오류이거나 자막을 찾을 수 없는 경우 Whisper로 폴백
        if _is_access_restricted_error(error_msg) or isinstance(e, (TranscriptsDisabled, NoTranscriptFound)):
            try:
                print(f"YouTube API 접근 제한 감지, Whisper로 폴백: {error_msg}")
                whisper_text = _download_audio_with_ytdlp(video_id)
                return whisper_text, "whisper"  # Whisper는 언어 자동 감지
            except Exception as whisper_error:
                # Whisper에서도 접근 제한 오류인지 확인
                whisper_error_msg = str(whisper_error)
                print(f"Whisper 폴백 시도 중 오류: {whisper_error_msg}")
                if _is_access_restricted_error(whisper_error_msg):
                    print(f"Whisper에서도 접근 제한 감지: {whisper_error_msg}")
                    raise Exception(f"YouTube API와 Whisper 모두 접근이 제한되었습니다. YouTube의 봇 감지로 인해 현재 요약을 생성할 수 없습니다. 잠시 후 다시 시도해 주세요.")
                else:
                    # Whisper에서 다른 종류의 오류 발생
                    print(f"Whisper 폴백 실패 (기타 오류): {whisper_error_msg}")
                    raise Exception(f"YouTube API 접근 제한으로 Whisper를 시도했지만 실패했습니다: {whisper_error_msg}")
        else:
            # 접근 제한이 아닌 다른 오류는 그대로 전파 (즉시 실패)
            print(f"접근 제한이 아닌 오류, 즉시 실패: {error_msg}")
            raise


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

