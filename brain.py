import time
import os
import requests
import json
import re
import warnings
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from bs4 import BeautifulSoup
import llm   # Gemini → LM Studio → OpenAI 자동 전환 계층
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=FutureWarning)

# --- [ 0. 환경 설정 ] ---
load_dotenv()
NAVER_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_SECRET = os.getenv("NAVER_CLIENT_SECRET")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
KMA_API_KEY = os.getenv("KMA_API_KEY")

HTTP_TIMEOUT = 10          # 모든 외부 호출 공통 타임아웃(초)
CYCLE_SECONDS = 600        # 수집 주기
USER_AGENT = "Mozilla/5.0 (compatible; AiKnowledgeBot/1.0)"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})

if not llm.available():
    print("⚠️ 사용 가능한 AI 제공자가 없습니다. 기본 키워드로만 수집합니다.")


DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# --- [ 1. 고정 수집 엔진: 날씨 & 주식 ] ---


# 공공데이터포털 단기예보 조회서비스 (VilageFcstInfoService_2.0)
# 격자 좌표: 서울특별시 = nx 60, ny 127 (활용가이드 격자_위경도 표 기준)
KMA_BASE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
KMA_NX, KMA_NY = 60, 127
# 단기예보 발표시각(1일 8회). API는 발표 10분 뒤부터 제공된다.
KMA_BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
KMA_SKY = {"1": "맑음", "3": "구름많음", "4": "흐림"}
KMA_PTY = {"0": "", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}


def _fmt_temp(value):
    """'30.0' -> '30' 처럼 불필요한 소수점을 정리."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(f)) if f == int(f) else f"{f:g}"


class KmaError(Exception):
    """기상청 API 호출 실패. 메시지에 인증키가 절대 들어가지 않도록 직접 구성한다."""


def _kma_base_datetime(now=None):
    """가장 최근에 '제공이 시작된' 발표시각을 (base_date, base_time)으로 반환."""
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    avail = now - timedelta(minutes=10)   # 발표 10분 후부터 제공
    for h in reversed(KMA_BASE_HOURS):
        if avail.hour >= h:
            return avail.strftime("%Y%m%d"), f"{h:02d}00"
    return (avail - timedelta(days=1)).strftime("%Y%m%d"), "2300"


def _kma_items(endpoint, params):
    """단기예보 API 호출 후 items 목록 반환.

    주의: requests의 기본 예외 메시지에는 serviceKey가 담긴 전체 URL이 포함된다.
    그대로 print하면 로그에 인증키가 남으므로, 여기서 메시지를 직접 만들어 던진다.
    """
    try:
        res = SESSION.get(f"{KMA_BASE}/{endpoint}", params=params, timeout=HTTP_TIMEOUT)
    except requests.RequestException as e:
        raise KmaError(f"{endpoint} 요청 실패({type(e).__name__})") from None
    if res.status_code != 200:
        hint = ""
        if res.status_code == 403:
            hint = " — data.go.kr에서 '단기예보 조회서비스' 활용신청이 승인됐는지, '디코딩된' 인증키인지 확인하세요."
        raise KmaError(f"{endpoint} HTTP {res.status_code}{hint}")
    try:
        payload = res.json()
    except ValueError:
        raise KmaError(f"{endpoint} 응답이 JSON이 아닙니다 (인증키 오류일 수 있음)") from None
    body = payload.get("response", {})
    header = body.get("header", {})
    code = header.get("resultCode")
    if code not in (None, "00", "0"):
        raise KmaError(f"{endpoint} 응답 코드 {code}: {header.get('resultMsg')}")
    items = body.get("body", {}).get("items", {}).get("item", [])
    return items if isinstance(items, list) else [items]


def fetch_kma_weather():
    """기상청 단기예보(공공데이터포털 VilageFcstInfoService_2.0).

    기존의 www.kma.go.kr RSS는 2021년에 폐지되어 HTML 안내 페이지만 반환한다.
    KMA_API_KEY가 없으면 조용히 건너뛴다.
    """
    if not KMA_API_KEY:
        return []
    base_date, base_time = _kma_base_datetime()
    params = {
        "serviceKey": KMA_API_KEY,   # data.go.kr의 '디코딩된' 일반 인증키를 쓸 것
        "pageNo": 1,
        "numOfRows": 1000,           # 한 발표분 전체를 받아 카테고리별로 골라 쓴다
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": KMA_NX,
        "ny": KMA_NY,
    }
    try:
        items = _kma_items("getVilageFcst", params)
    except KmaError as e:
        print(f"⚠️ 기상청 단기예보 수집 실패: {e}")
        return []
    if not items:
        print("💡 기상청 API: 예보 항목이 비어 있습니다.")
        return []

    # 가장 이른 예보일자 = 오늘(또는 다음 예보일) 기준으로 정리
    target_date = min(i.get("fcstDate", "") for i in items if i.get("fcstDate"))
    today = [i for i in items if i.get("fcstDate") == target_date]
    today.sort(key=lambda i: i.get("fcstTime", ""))

    def first(category):
        for i in today:
            if i.get("category") == category:
                return str(i.get("fcstValue", "")).strip()
        return ""

    sky = KMA_SKY.get(first("SKY"), "")
    pty = KMA_PTY.get(first("PTY"), "")
    wf = pty or sky
    if not wf:
        print("💡 기상청 API: 하늘상태/강수형태를 찾지 못했습니다.")
        return []

    # 발표시각에 따라 이미 지난 TMN(일 최저기온)은 응답에 없을 수 있으므로 있는 것만 쓴다
    tmp, tmn, tmx, pop = first("TMP"), first("TMN"), first("TMX"), first("POP")
    parts = []
    if tmp:
        parts.append(f"기온 {_fmt_temp(tmp)}℃")
    if tmn:
        parts.append(f"최저 {_fmt_temp(tmn)}℃")
    if tmx:
        parts.append(f"최고 {_fmt_temp(tmx)}℃")
    if pop:
        parts.append(f"강수확률 {pop}%")
    parts.append(f"({base_date} {base_time} 발표)")

    return [{
        "source": "KMA-Weather",
        "title": f"[날씨] 서울: {wf}",
        "description": " / ".join(parts),
        "date": datetime.now().strftime('%Y-%m-%d %H:%M'),
    }]


def fetch_stock_market():
    url = "https://finance.naver.com/news/mainnews.naver"
    try:
        res = SESSION.get(url, timeout=HTTP_TIMEOUT)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠️ 증시 뉴스 수집 실패: {e}")
        return []
    soup = BeautifulSoup(res.text, "html.parser")
    titles = soup.select(".articleSubject a")
    return [{
        "source": "Finance",
        "title": f"[증시] {t.get_text().strip()}",
        "description": "네이버 금융 실시간 주요 뉴스",
        "date": datetime.now().strftime('%Y-%m-%d')
    } for t in titles[:5] if t.get_text().strip()]


# --- [ 2. AI 주제 선정: 상태 확인 로그 추가 ] ---

def get_smart_topics():
    # 기본 방어 키워드
    base_topics = ["인공지능", "반도체", "엔비디아", "국내 증시", "나스닥", "KBO", "SK하이닉스", "삼성전자", "NC다이노스"]

    if not llm.available():
        return base_topics

    try:
        # 뉴스 랭킹 제목 수집
        url = "https://news.naver.com/main/ranking/popularDay.naver"
        res = SESSION.get(url, timeout=HTTP_TIMEOUT)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        titles = [t.get_text() for t in soup.select(".rankingnews_list .list_title")[:10]]

        # AI 호출 시도 (실패 시 llm 모듈이 다음 제공자로 자동 전환)
        prompt = f"다음 뉴스 제목들을 분석해서 지식 가치가 높은 주제 5개만 쉼표로 구분해서 뽑아줘: {', '.join(titles)}"
        answer, _provider = llm.generate(prompt, timeout_ms=30_000)

        if answer:
            raw_text = answer.replace("\n", " ")

            # AI가 번호를 매기거나 설명을 붙이는 경우를 대비해 핵심 키워드만 추출 시도
            if ":" in raw_text:
                raw_text = raw_text.split(":")[-1]

            # 불필요한 따옴표나 특수문자 제거
            raw_text = re.sub(r'[*#\"\'\d\.]', '', raw_text)

            ai_keywords = [k.strip() for k in re.split(r'[,|·]', raw_text) if len(k.strip()) > 1]
            # 검색어로 쓸 수 없는 길거나 이상한 문자열은 버린다
            ai_keywords = [k for k in ai_keywords if len(k) <= 40]

            if ai_keywords:
                # ✨ AI 작동 확인 로그
                print(f"✨ AI 추천 키워드 정제 성공: {ai_keywords[:5]}")
                return list(dict.fromkeys(base_topics + ai_keywords))[:10]
            else:
                print("💡 AI 상태: 응답에서 키워드를 추출하지 못함")
        else:
            print("💡 AI 상태: 응답 결과가 없거나 안전 필터에 의해 차단됨")

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

def _normalize_title(value):
    return re.sub(r'\s+', '', str(value))


def save_to_json(filename, new_data):
    if not new_data:
        return
    path = os.path.join(DATA_DIR, f"{filename}.json")
    old_data = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                old_data = loaded
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"⚠️ {filename}.json 읽기 실패, 새로 시작합니다: {e}")

    existing_titles = {
        _normalize_title(x["title"])
        for x in old_data
        if isinstance(x, dict) and x.get("title")
    }
    added_count = 0
    for item in new_data:
        title = item.get("title") if isinstance(item, dict) else None
        if not title:
            continue
        key = _normalize_title(title)
        if key in existing_titles:
            continue
        existing_titles.add(key)
        old_data.append(item)
        added_count += 1

    if added_count > 0:
        # 임시 파일 → os.replace 로 원자적 교체 (중간에 죽어도 파일이 깨지지 않음)
        tmp_path = f"{path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(old_data, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
            print(f"📁 {filename}.json: +{added_count}개 신규 저장")
        except OSError as e:
            print(f"⚠️ {filename}.json 저장 실패: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


def search_routine(topic):
    n_news, g_search = [], []

    # 네이버 (검색어는 반드시 URL 인코딩해야 파라미터가 오염되지 않는다)
    if NAVER_ID and NAVER_SECRET:
        try:
            query = urlencode({"query": topic, "display": 3})
            n_res = SESSION.get(
                f"https://openapi.naver.com/v1/search/news.json?{query}",
                headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET},
                timeout=HTTP_TIMEOUT,
            )
            if n_res.status_code == 200:
                n_news = [
                    {"source": "Naver", "title": i.get("title", ""), "description": i.get("description", "")}
                    for i in n_res.json().get("items", [])
                ]
            else:
                print(f"💡 네이버 API 응답 {n_res.status_code} ({topic})")
        except (requests.RequestException, ValueError) as e:
            print(f"⚠️ 네이버 검색 실패({topic}): {e}")

    # 구글 (Serper)
    if SERPER_API_KEY:
        try:
            g_res = SESSION.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_API_KEY},
                json={"q": topic, "num": 2},
                timeout=HTTP_TIMEOUT,
            )
            if g_res.status_code == 200:
                g_search = [
                    {"source": "Google", "title": i.get("title", ""), "description": i.get("snippet", "")}
                    for i in g_res.json().get("organic", [])
                ]
            elif g_res.status_code == 400 and "credits" in g_res.text:
                print("💡 Serper API: 할당량 소진 (네이버 검색만 수행)")
            else:
                print(f"💡 Serper API 응답 {g_res.status_code} ({topic})")
        except (requests.RequestException, ValueError) as e:
            print(f"⚠️ Serper API 연결 실패: {e}")

    return n_news, g_search


def run_cycle():
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


# --- [ 4. 메인 루프 (10분 주기) ] ---

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 자율 지식 학습 시스템 v3.3 (상태 모니터링 모드)")
    print("=" * 50)

    if not (NAVER_ID and NAVER_SECRET):
        print("⚠️ NAVER_CLIENT_ID/SECRET 미설정: 네이버 뉴스 수집을 건너뜁니다.")
    if not SERPER_API_KEY:
        print("⚠️ SERPER_API_KEY 미설정: 구글 검색 수집을 건너뜁니다.")
    if not KMA_API_KEY:
        print("⚠️ KMA_API_KEY 미설정: 날씨 수집을 건너뜁니다.")

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔄 정기 수집 루틴 시작")
        try:
            run_cycle()
            print("✅ 루틴 완료. 10분 대기 후 재시작합니다.")
        except KeyboardInterrupt:
            print("\n👋 종료합니다.")
            break
        except Exception as e:
            # 어떤 예외도 수집 데몬을 죽이지 못하게 한다
            print(f"❌ 루틴 중 예기치 못한 오류: {e} — 다음 주기에 재시도합니다.")
        time.sleep(CYCLE_SECONDS)
