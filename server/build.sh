#!/bin/bash
# Render 빌드 스크립트

echo "🚀 YouTube Summary API 빌드 시작..."

# Python 버전 확인
python --version

# pip 업그레이드
pip install --upgrade pip

# 의존성 설치
echo "📦 의존성 설치 중..."
pip install -r requirements.txt

# 선택적 의존성 설치 (실패해도 계속)
echo "🔧 선택적 의존성 설치 시도..."
pip install selenium==4.15.0 || echo "Selenium 설치 실패 (선택적)"
pip install undetected-chromedriver==3.5.4 || echo "undetected-chromedriver 설치 실패 (선택적)"
pip install playwright==1.40.0 || echo "Playwright 설치 실패 (선택적)"
pip install requests-html==0.10.0 || echo "requests-html 설치 실패 (선택적)"

# Playwright 브라우저 설치 (선택적)
python -c "import playwright; playwright.install()" 2>/dev/null || echo "Playwright 브라우저 설치 실패 (선택적)"

echo "✅ 빌드 완료!"
