# 🧠 나만의 AI 지식 창고 (Personal AI Knowledge Base)

**"잠들지 않는 AI가 스스로 뉴스를 읽고, 나의 지식과 결합하여 답변합니다."**

본 프로젝트는 사용자의 개인 문서(PDF, TXT)와 AI가 실시간으로 수집한 외부 정보(뉴스, 날씨, 증시)를 통합하여 관리하는 **지능형 RAG(Retrieval-Augmented Generation) 시스템**입니다. `brain.py`를 통해 10분마다 세상의 변화를 학습하고, `app.py`의 Streamlit 인터페이스를 통해 대화형으로 지식을 인출합니다.

---

## ✨ 핵심 기능 (Key Features)

### 1. 자율 지식 학습 시스템 (`brain.py`)
* **스마트 주제 선정**: Gemini 1.5 Flash 모델이 현재 네이버 뉴스 랭킹을 분석하여 학습 가치가 높은 키워드를 스스로 추출합니다.
* **다중 소스 수집**: Naver Search API, Google Serper API를 활용하여 최신 뉴스와 웹 정보를 수집합니다.
* **실시간 데이터 고정 수집**: 기상청 RSS를 통한 날씨 정보 및 네이버 금융의 주요 증시 뉴스를 주기적으로 업데이트합니다.
* **자동 아카이빙**: 수집된 데이터는 `data/` 디렉토리에 JSON 형태로 자동 저장됩니다.

### 2. 지능형 검색 및 대화 (`app.py`)
* **로컬 RAG 엔진**: FAISS(Facebook AI Similarity Search)와 `SentenceTransformer`를 사용하여 수집된 방대한 지식 중 질문과 가장 관련 있는 내용을 초고속으로 검색합니다.
* **멀티 포맷 지원**: 사용자가 직접 업로드한 PDF, TXT 파일은 물론 시스템이 수집한 JSON 지식까지 통합 검색합니다.
* **보안 및 안정성**: 
    * **Rate Limit**: 무분별한 API 호출 방지를 위한 전송 간격 제한.
    * **Sanitize**: 프롬프트 인젝션 및 악성 스크립트 방어 로직.
    * **Auto Model Selection**: 사용 가능한 Gemini 모델(1.5-Flash, Pro 등)을 자동으로 감지하여 최적의 경로로 응답합니다.

---

## 🛠 기술 스택 (Tech Stack)

| 구분 | 기술 |
| :--- | :--- |
| **Frontend** | Streamlit |
| **LLM** | Google Gemini (1.5 Flash / Pro) |
| **Vector DB** | FAISS (Vector Indexing) |
| **Embedding** | SentenceTransformer (`paraphrase-multilingual-MiniLM-L12-v2`) |
| **Data Processing** | BeautifulSoup4, pdfplumber, Pandas, NumPy |
| **APIs** | Naver Search, Google Serper, KMA RSS |

---

## 🚀 시작하기 (Quick Start)

### 1. 환경 설정
`.env` 파일을 생성하고 필요한 API 키를 입력합니다.
```env
GOOGLE_API_KEY=your_gemini_api_key
NAVER_CLIENT_ID=your_naver_id
NAVER_CLIENT_SECRET=your_naver_secret
SERPER_API_KEY=your_google_serper_key
```

### 2. 지식 수집 엔진 가동 (Background)
AI가 스스로 정보를 수집하도록 백그라운드에서 실행합니다.
```bash
python brain.py
```

### 3. 웹 인터페이스 실행
수집된 지식을 바탕으로 대화를 시작합니다.
```bash
streamlit run app.py
```

---

## 📂 프로젝트 구조
* `app.py`: Streamlit 기반 웹 인터페이스 및 RAG 검색 로직.
* `brain.py`: 자율 주제 선정 및 실시간 데이터 크롤링 엔진.
* `data/`: 수집된 JSON 지식 및 사용자 문서가 저장되는 공간.
* `faiss_index.bin`: 검색을 위한 벡터 인덱스 파일.
* `chat_history.json`: 대화 목록 및 메시지 기록 저장.

---

## 🛡 보안 및 시스템 지침
* 본 어시스턴트는 제공된 지식 데이터를 최우선으로 참고합니다.
* 시스템 설정 변경 시도나 악의적인 명령(Prompt Injection)을 거부하도록 설계되었습니다.
* 한국어 환경에 최적화된 다국어 임베딩 모델을 사용합니다.

---

### 💡 Tip
`brain.py`를 서버에서 24시간 가동하면, 시간이 지날수록 당신만의 거대한 지식 베이스가 구축됩니다. 주기적으로 **"지식 새로고침"** 버튼을 눌러 최신 데이터를 벡터 엔진에 반영하세요!

---
**Author:** 강민제(Kangminje)
**License:** MIT

---
