import time
import os
import requests
import json
import re
import random
import warnings
from datetime import datetime
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=FutureWarning)

# --- [ 0. 환경 설정 ] ---
load_dotenv()
NAVER_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_SECRET = os.getenv("NAVER_CLIENT_SECRET")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def select_model():
    try:
        available_models = [m.name for m in genai.list_models() 
                            if 'generateContent' in m.supported_generation_methods]
        for preferred in ["models/gemini-1.5-flash", "models/gemini-pro"]:
            if preferred in available_models:
                return preferred
        return available_models[0] if available_models else "models/gemini-pro"
    except:
        return "models/gemini-pro"

SELECTED_MODEL = select_model()

DATA_DIR = "data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# --- [ 1. 고정 수집 엔진: 날씨 & 주식 ] ---

def fetch_kma_weather():
    try:
        url = "http://www.kma.go.kr/weather/forecast/mid-term-rss3.jsp?stnId=108"
        res = requests.get(url, timeout=10)
        soup = BeautifulSoup(res.text, "xml")
        location = soup.find("location", province="서울ㆍ인천ㆍ경기도")
        if location:
            data = location.find("data")
            return [{
                "source": "KMA-Weather",
                "title": f"[날씨] 서울/경기: {data.find('wf').text}",
                "description": f"기온: {data.find('tmn').text}℃ ~ {data.find('tmx').text}℃",
                "date": datetime.now().strftime('%Y-%m-%d %H:%M')
            }]
    except: pass
    return []

def fetch_stock_market():
    try:
        url = "https://finance.naver.com/news/mainnews.naver"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        titles = soup.select(".articleSubject a")
        return [{
            "source": "Finance",
            "title": f"[증시] {t.get_text().strip()}",
            "description": "네이버 금융 실시간 주요 뉴스",
            "date": datetime.now().strftime('%Y-%m-%d')
        } for t in titles[:5]]
    except: pass
    return []

# --- [ 2. AI 주제 선정: 상태 확인 로그 추가 ] ---

def get_smart_topics():
    # 기본 방어 키워드
    base_topics = ["인공지능", "반도체", "엔비디아", "국내 증시", "나스닥", "KBO", "SK하이닉스", "삼성전자", "NC다이노스"]
    
    try:
        # 뉴스 랭킹 제목 수집
        url = "https://news.naver.com/main/ranking/popularDay.naver"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        titles = [t.get_text() for t in soup.select(".rankingnews_list .list_title")[:10]]
        
        # AI 호출 시도
        model = genai.GenerativeModel(SELECTED_MODEL) 
        prompt = f"다음 뉴스 키워드들을 분석해서 지식 가치가 높은 주제 5개만 쉼표로 구분해서 뽑아줘: {', '.join(titles)}"
        response = model.generate_content(prompt)
        
        if response and response.text:
            # ✨ 콤마로 구분된 텍스트만 추출하기 위한 정규식 또는 정제
            raw_text = response.text.replace("\n", " ")
            # AI가 번호를 매기거나 설명을 붙이는 경우를 대비해 핵심 키워드만 추출 시도
            if ":" in raw_text: raw_text = raw_text.split(":")[-1]
            
            ai_keywords = [k.strip() for k in re.split(r'[,|·]', raw_text) if len(k.strip()) > 1]
            # ✨ AI 작동 확인 로그
            print(f"✨ AI 추천 키워드 정제 성공: {ai_keywords[:5]}")
            return list(set(base_topics + ai_keywords))[:10]
            
    except Exception as e:
        # 💡 AI 실패 원인 출력 (429 할당량 초과 등 확인용)
        if "429" in str(e):
            print("💡 AI 상태: 할당량 초과로 휴식 중 (기본 키워드로 진행)")
        elif "404" in str(e):
            print("💡 AI 상태: 모델 경로 오류 (기본 키워드로 진행)")
        else:
            print(f"💡 AI 상태: 일시적 오류({e}) (기본 키워드로 진행)")
            
    return base_topics

# --- [ 3. 공통 저장 및 검색 루틴 ] ---

def save_to_json(filename, new_data):
    if not new_data: return
    path = os.path.join(DATA_DIR, f"{filename}.json")
    old_data = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f: old_data = json.load(f)
        except: pass
    
    existing_titles = {re.sub(r'\s+', '', str(x['title'])) for x in old_data}
    added_count = 0
    for item in new_data:
        if re.sub(r'\s+', '', str(item['title'])) not in existing_titles:
            old_data.append(item)
            added_count += 1
            
    if added_count > 0:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(old_data, f, ensure_ascii=False, indent=4)
        print(f"📁 {filename}.json: +{added_count}개 신규 저장")

def search_routine(topic):
    # 네이버
    n_res = requests.get(
        f"https://openapi.naver.com/v1/search/news.json?query={topic}&display=3",
        headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    )
    n_news = [{"source": "Naver", "title": i['title'], "description": i['description']} for i in n_res.json().get('items', [])] if n_res.status_code == 200 else []
    
    # 구글 (Serper)
    g_search = []
    try:
        g_res = requests.post(
            "https://google.serper.dev/search", 
            headers={"X-API-KEY": SERPER_API_KEY}, 
            json={"q": topic, "num": 2},
            timeout=5
        )
        if g_res.status_code == 200:
            g_search = [{"source": "Google", "title": i['title'], "description": i.get('snippet', '')} for i in g_res.json().get('organic', [])]
        elif g_res.status_code == 400 and "credits" in g_res.text:
            print(f"💡 Serper API: 할당량 소진 (네이버 검색만 수행)")
    except Exception as e:
        print(f"⚠️ Serper API 연결 실패: {e}")
    
    return n_news, g_search

# --- [ 4. 메인 루프 (10분 주기) ] ---

if __name__ == "__main__":
    print("="*50)
    print("🤖 자율 지식 학습 시스템 v3.2 (상태 모니터링 모드)")
    print("="*50)
    
    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔄 정기 수집 루틴 시작")

        # 1. 고정 데이터
        save_to_json("KMA-Weather", fetch_kma_weather())
        save_to_json("Stock-Market", fetch_stock_market())

        # 2. 스마트 주제 선정 및 수집
        topics = get_smart_topics()
        print(f"🎯 현재 탐색 주제: {topics}")
        
        for t in topics:
            news, web = search_routine(t)
            save_to_json("Naver-News", news)
            save_to_json("Google-Search", web)
            time.sleep(1)
            
        print(f"✅ 루틴 완료. 10분 대기 후 재시작합니다.")
        time.sleep(600)