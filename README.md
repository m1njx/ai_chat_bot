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

### 3. 강력한 보안 및 방어 체계
- **프롬프트 인젝션 방어**: 악의적인 명령어 우회 시도를 탐지하고 차단합니다.
- **입출력 필터링**: 민감한 정보 유출 방지 및 위험한 스크립트 실행을 차단합니다.
- **Rate Limit**: 무분별한 API 호출을 방지하기 위한 속도 제한이 적용되어 있습니다.

### 4. 자율형 데이터 수집 (Autonomous Brain)
- `brain.py`가 백그라운드에서 주기적으로 새로운 뉴스 및 주식 정보를 수집하여 지식 창고를 항상 최신 상태로 유지합니다.

## 🛠 Tech Stack

- **Frontend**: Streamlit
- **AI Model**: Google Gemini 1.5 Flash / Pro
- **Vector DB**: FAISS
- **Embedding**: Sentence-Transformers (Multilingual-MiniLM)
- **Data Parsing**: BeautifulSoup4, pdfplumber
- **Language**: Python 3.9+

## 🚀 시작하기

### 1. 환경 변수 설정
`.env` 파일을 생성하고 필요한 API 키를 입력합니다.
```env
GOOGLE_API_KEY=your_gemini_api_key
NAVER_CLIENT_ID=your_naver_id
NAVER_CLIENT_SECRET=your_naver_secret
SERPER_API_KEY=your_serper_key
```

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

## 📂 프로젝트 구조
- `app.py`: 토스 스타일 UI 및 채팅 비즈니스 로직.
- `brain.py`: 뉴스/데이터 수집 및 키워드 추출 엔진.
- `data/`: 수집된 지식(JSON, PDF, TXT)이 저장되는 디렉토리.
- `faiss_index.bin`: 검색을 위한 벡터 인덱스 파일.

---
Developed with ❤️ by Antigravity AI
