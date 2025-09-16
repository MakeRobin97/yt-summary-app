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
        "openai": os.getenv("OPENAI_API_KEY") is not None,
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
            if any(tok in msg for tok in ["Too Many Requests", "429", "sorry/index"]):
                continue
            raise
    raise last_err


def fetch_transcript_text(video_id: str) -> tuple[str, Optional[str]]:
    _apply_optional_proxy_from_env()
    # youtube-transcript-api는 정적 메서드 list_transcripts(video_id)를 사용합니다.
    transcript_list = _with_backoff(YouTubeTranscriptApi.list_transcripts, video_id)
    lang_code: Optional[str] = None
    transcript = None

    # 우선순위: 한국어 -> 영어
    for target in ["ko", "en"]:
        try:
            transcript = transcript_list.find_manually_created_transcript([target])
            lang_code = target
            break
        except Exception:
            try:
                transcript = transcript_list.find_transcript([target])
                lang_code = target
                break
            except Exception:
                continue

    if transcript is None:
        # 자동 번역으로 한국어 우선 시도, 실패 시 영어 자동 생성본
        try:
            transcript = transcript_list.find_transcript(["en"]).translate("ko")
            lang_code = "ko"
        except Exception:
            try:
                transcript = transcript_list.find_transcript(["en"])
                lang_code = "en"
            except Exception:
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

