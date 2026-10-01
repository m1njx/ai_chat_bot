# 🧠 나만의 AI 지식 창고 (My AI Knowledge Bot)

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Gemini%20AI-4285F4?style=for-the-badge&logo=google-gemini&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Toss Design](https://img.shields.io/badge/Design-Toss%20Style-blue?style=for-the-badge)

흩어져 있는 뉴스와 정보, 그리고 나의 개인적인 문서들을 하나로 모아 AI가 답변해 주는 **나만의 지능형 지식 창고**입니다. 토스(Toss) 스타일의 프리미엄 UI와 강력한 RAG(Retrieval-Augmented Generation) 엔진을 탑재했습니다.

## ✨ 주요 기능

### 1. 토스(Toss) 스타일의 프리미엄 UI/UX
- **미니멀리즘 디자인**: 토스 앱의 감성을 그대로 담은 깔끔하고 직관적인 인터페이스.
- **다크 모드 완벽 지원**: 시스템 설정에 따라 라이트/다크 모드로 자동 전환됩니다.
- **Pretendard 서체**: 가독성 높은 폰트와 부드러운 애니메이션 적용.

### 2. 지능형 지식 통합 (RAG Engine)
- **멀티 소스 지원**: PDF, TXT 파일은 물론 네이버 뉴스, 주식 시장 데이터(JSON)까지 통합 관리합니다.
- **FAISS 벡터 검색**: 방대한 데이터 속에서 질문과 가장 관련 있는 정보를 빛의 속도로 찾아냅니다.
- **지식 대시보드**: 현재 저장된 지식 통계를 한눈에 확인하고, 버튼 하나로 실시간 동기화가 가능합니다.

### 3. 보안 및 방어 체계
- **프롬프트 인젝션 방어**: 사용자 입력은 패턴 탐지 후 차단하고, 외부에서 수집한 문서(뉴스·검색 스니펫)는 컨텍스트에 넣기 전 무력화합니다(간접 인젝션 방어).
- **HTML 이스케이프**: 수집 콘텐츠와 사용자가 지은 대화 제목은 화면에 렌더링하기 전 모두 이스케이프합니다.
- **출력 필터링**: 응답에 API 키·비밀값이 섞여 나오면 마스킹합니다.
- **Rate Limit**: 세션 단위로 채팅 60초당 10회, 지식 재구축 300초당 2회로 제한합니다.
- **접근 제어(선택)**: `APP_PASSWORD`를 설정하면 비밀번호 게이트가 켜지고, 대화 기록이 브라우저 세션별로 분리됩니다. 설정하지 않으면 로컬 단독 사용 모드로 동작합니다.

> ⚠️ `APP_PASSWORD` 없이 공개 배포하면 접속자 모두가 **하나의 대화 기록을 공유**합니다. 인터넷에 올릴 때는 반드시 설정하세요.

### 4. LLM 자동 전환 (Failover)
`llm.py`가 여러 제공자를 순서대로 시도합니다. 기본 순서는 **Gemini → LM Studio(로컬) → OpenAI**이며,
앞 순서가 호출 오류·할당량 초과(429)·타임아웃·안전필터 차단 등 어떤 이유로든 실패하면 자동으로 다음으로 넘어갑니다.

- **LM Studio**: 앱의 `Developer` 탭에서 Status를 **Running**으로 켜고 모델을 로드하면 됩니다(기본 `http://localhost:1234/v1`). 무료이고 인터넷이 필요 없습니다. 꺼져 있으면 연결이 즉시 거부되어 비용 없이 건너뜁니다.
- **OpenAI**: `OPENAI_API_KEY`가 필요하며, **선불 크레딧이 있어야 동작합니다**(크레딧 0이면 429).
- 순서는 `LLM_ORDER` 환경변수로 바꿀 수 있습니다. 예: `LLM_ORDER=lmstudio,gemini`

### 4. 자율형 데이터 수집 (Autonomous Brain)
- `brain.py`가 백그라운드에서 주기적으로 새로운 뉴스 및 주식 정보를 수집하여 지식 창고를 항상 최신 상태로 유지합니다.

## 🛠 Tech Stack

- **Frontend**: React 19 + Vite (`frontend/`) · Streamlit(`app.py`, 단일 파일 실행용으로 유지)
- **Backend**: FastAPI + SSE 스트리밍 (`api.py`)
- **AI Model**: Google Gemini (주) / LM Studio 로컬 LLM · OpenAI (예비, 자동 전환)
- **Vector DB**: FAISS
- **Embedding**: Sentence-Transformers (Multilingual-MiniLM)
- **Data Parsing**: BeautifulSoup4, pdfplumber
- **Language**: Python 3.11+ (numpy 2.4 요구사항)

## 🚀 시작하기

### 1. 환경 변수 설정
`.env` 파일을 생성하고 필요한 API 키를 입력합니다.
```env
GOOGLE_API_KEY=your_gemini_api_key
NAVER_CLIENT_ID=your_naver_id
NAVER_CLIENT_SECRET=your_naver_secret
SERPER_API_KEY=your_serper_key
KMA_API_KEY=your_kma_service_key   # 선택: 날씨 수집용 (공공데이터포털)
APP_PASSWORD=                      # 공개 배포 시 필수
```

전체 항목은 [.env.example](.env.example)을 참고하세요.

> **날씨 수집**: 기상청의 옛 RSS(`www.kma.go.kr/.../mid-term-rss3.jsp`)는 2021년에 폐지되었습니다.
> 현재는 [공공데이터포털](https://www.data.go.kr/)의 **단기예보 조회서비스**(`VilageFcstInfoService_2.0`)
> 인증키(`KMA_API_KEY`)를 사용하며, **디코딩된 일반 인증키**를 넣어야 합니다.
> 서울(격자 nx=60, ny=127) 기준으로 하늘상태·기온·강수확률을 수집하며, 키가 없으면 날씨 항목만 조용히 건너뜁니다.

### 2. 필수 라이브러리 설치
```bash
pip install -r requirements.txt
```

### 3. 서비스 실행
- **지식 수집 엔진 실행 (백그라운드)**
```bash
python brain.py
```
- **채팅 웹 앱 실행**
```bash
streamlit run app.py
```

## 🏗 아키텍처 (프론트/백 분리)

```
[React + Vite]  ──HTTP/SSE──▶  [FastAPI api.py]  ──▶  core.py ──┬─▶ FAISS 인덱스
   (Vercel 등)                    (Render)                       ├─▶ chat_history.json
                                                                 └─▶ llm.py ─▶ Gemini/LM Studio/OpenAI
```

Streamlit판(`app.py`)도 같은 `core.py`를 쓰므로 계속 동작합니다. 두 UI가 대화 기록을 공유합니다.

### 로컬 실행

```bash
# 1) 백엔드
uvicorn api:app --reload --port 8000

# 2) 프론트엔드 (별도 터미널)
cd frontend && npm install && npm run dev     # http://localhost:5173

# (선택) Streamlit판
streamlit run app.py
```

`frontend/.env`에 `VITE_API_BASE=http://127.0.0.1:8000`을 넣으면 백엔드 주소를 바꿀 수 있습니다(기본값도 동일).

### 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/session` | 인증 필요 여부·제공자 순서 |
| POST | `/api/auth/login` | 비밀번호 로그인 → Bearer 토큰 |
| GET/POST | `/api/chats` | 대화 목록 조회 / 생성 |
| PATCH/DELETE | `/api/chats/{id}` | 이름 변경 / 삭제 |
| POST | `/api/chat/stream` | **SSE 스트리밍 응답** |
| GET | `/api/knowledge` | 지식 통계·샘플 |
| POST | `/api/knowledge/refresh` | 인덱스 재구축 (요청 제한 있음) |

### 성능 관련

- **응답 스트리밍**: 답변을 글자 단위로 즉시 표시합니다. Streamlit판은 전체 응답을 기다린 뒤 한 번에 출력했습니다.
- **인덱스 캐싱**: FAISS 인덱스와 문서 JSON을 파일 mtime 기준으로 캐시합니다. Streamlit판은 상호작용마다 디스크에서 다시 읽었습니다.

## 🌐 Render 배포 가이드 (Deployment)

본 프로젝트는 **Render.com**에 최적화되어 있습니다.

1. **배포 방식**: Render에서 `Web Service`를 선택합니다.
2. **Runtime**: `Python`으로 설정합니다.
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `sh start.sh`
5. **Environment Variables**: `.env`에 있는 모든 API 키를 Render의 Dashboard -> Env Vars 항목에 추가해 주세요. `PORT`는 Render가 자동 주입하므로 직접 설정하지 마세요.
   - **`CORS_ORIGINS`에 프론트엔드 배포 주소를 반드시 넣으세요.** 없으면 브라우저가 API 요청을 차단합니다.
   - `SECRET_KEY`를 설정해야 재배포 후에도 로그인이 유지됩니다.

### 프론트엔드 배포 (Vercel 등)

- **Root Directory**: `frontend`
- **Build Command**: `npm run build` / **Output Directory**: `dist`
- **환경 변수**: `VITE_API_BASE=https://<렌더-백엔드>.onrender.com`
6. **Python 버전**: `render.yaml`에 `PYTHON_VERSION=3.11.9`가 지정되어 있습니다. 3.10 이하로 낮추면 `numpy` 설치가 실패합니다.
7. **APP_PASSWORD**: 공개 URL이 생기므로 반드시 설정하세요.

> **주의**: `Publish directory dist does not exist!` 에러가 발생한다면, Render 설정에서 `Static Site`가 아닌 `Web Service`를 선택했는지 확인해 주세요.

> **무료 플랜의 한계 (중요)**
> - Render 무료 인스턴스는 **파일 시스템이 휘발성**입니다. 재배포·재시작 시 `data/`, `faiss_index.bin`, `chat_history.json`이 **모두 사라집니다.** 데이터를 유지하려면 유료 Persistent Disk나 외부 스토리지가 필요합니다.
> - `brain.py`가 10분마다 무한히 외부 API를 호출하므로 Gemini/Serper 무료 할당량을 지속적으로 소모합니다. 주기는 `brain.py`의 `CYCLE_SECONDS`로 조절할 수 있습니다.

## 📂 프로젝트 구조
- `core.py`: UI에 의존하지 않는 공통 로직 — 입력 정제·인젝션 방어·출력 필터·RAG 검색·대화 저장소. **FastAPI와 Streamlit이 이 파일을 공유**하므로 두 프론트의 보안 정책이 갈라지지 않습니다.
- `api.py`: FastAPI 백엔드. JSON API + SSE 스트리밍.
- `llm.py`: LLM 제공자 자동 전환 계층 (Gemini / LM Studio / OpenAI). 스트리밍 지원.
- `brain.py`: 뉴스/데이터 수집 및 키워드 추출 엔진.
- `app.py`: Streamlit UI (유지). `core.py`를 그대로 사용합니다.
- `frontend/`: React + Vite 프론트엔드.
- `data/`: 수집된 지식(JSON, PDF, TXT)이 저장되는 디렉토리.
- `faiss_index.bin`: 검색을 위한 벡터 인덱스 파일.

---
Developed with ❤️ by Antigravity AI
