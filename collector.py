import email.utils
import html
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from google import genai
import requests

# 1. 환경변수 확인
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

# 2. 부서 매핑 룰 ('특례시' 단독 키워드 제거 및 실무 핵심어 보강)
DEPT_RULES = [
    {"dept": "공보실 언론담당관", "keywords": ["시정보도", "기자회견", "기자브리핑", "기획보도", "시보", "취재지원"]},
    {"dept": "공보실 홍보담당관", "keywords": ["시정홍보", "도시브랜드", "시정소식지", "홍보대사", "전광판", "유튜브"]},
    {"dept": "감사관", "keywords": ["자체감사", "공직기강", "공무원비리", "징계처분", "청렴도", "부패방지", "시민옴부즈만"]},
    {"dept": "트램건설추진단", "keywords": ["동탄트램", "트램", "도시철도", "트램차량기지", "트램노선"]},
    {"dept": "AI스마트전략실", "keywords": ["스마트도시", "빅데이터", "스마트도시통합운영센터", "데이터플랫폼", "공공데이터"]},
    {"dept": "기본사회담당관", "keywords": ["기본사회", "기본소득", "사회적경제", "협동조합", "마을기업", "공정무역"]},
    {"dept": "기획조정실 정책기획관", "keywords": ["시정종합기획", "주요업무계획", "공약사항", "화성시연구원", "공모사업총괄"]},
    {"dept": "기획조정실 균형발전과", "keywords": ["균형발전", "국제테마파크", "테크노폴", "경제자유구역", "권역별발전"]},
    {"dept": "기획조정실 의회법무과", "keywords": ["시의회", "행정사무감사", "조례규칙", "행정소송", "행정심판", "규제개혁"]},
    {"dept": "기획조정실 군공항대응과", "keywords": ["군공항", "수원군공항", "화옹지구", "군비행장소음", "소음피해보상", "군공항이전"]},
    {"dept": "기획조정실 정보통신과", "keywords": ["정보통신", "행정전산망", "사이버보안", "공공와이파이", "자가통신망"]},
    {"dept": "안전건설실 안전정책과", "keywords": ["재난안전관리", "중대재해", "중대시민재해", "시민안전교육", "민방위"]},
    {"dept": "안전건설실 재난대응과", "keywords": ["자연재난", "사회재난", "재난안전대책본부", "수방자재", "재해구호물자", "자율방재단"]},
    {"dept": "안전건설실 건설과", "keywords": ["전문건설업", "국가하천", "소하천정비", "배수펌프장", "농업생산기반"]},
    {"dept": "안전건설실 도로과", "keywords": ["광역도로망", "국도", "지방도", "도시계획도로", "도로개설", "과적단속", "도로제설"]},
    {"dept": "자치행정국 행정지원과", "keywords": ["청사방호", "공무원복무", "공무직노조", "의전", "기록물관리", "후생복지"]},
    {"dept": "자치행정국 자치분권과", "keywords": ["자치분권", "지방자치", "특례시법", "특례권한", "대도시특례", "구청설치", "행정구역개편", "고향사랑기부제"]},
    {"dept": "자치행정국 시민협력과", "keywords": ["주민자치회", "주민자치센터", "마을공동체", "자원봉사센터", "자율방범대"]},
    {"dept": "자치행정국 인사과", "keywords": ["공무원인사", "공무원채용", "승진심사", "성과상여금", "공무원교육훈련"]},
    {"dept": "재정국 예산재정과", "keywords": ["지방예산", "추경예산", "지방교부세", "국도비확보", "주민참여예산"]},
    {"dept": "돌봄복지국 복지정책과", "keywords": ["기초생활보장", "기초수급자", "사회복지기금", "의료급여", "보훈단체", "자활근로"]},
    {"dept": "돌봄복지국 통합돌봄과", "keywords": ["통합돌봄", "복지사각지대", "고독사예방", "긴급복지지원", "위기가구발굴"]},
    {"dept": "돌봄복지국 장애인복지과", "keywords": ["장애인복지", "장애인연금", "장애인일자리", "장애인복지관", "발달장애인"]},
    {"dept": "돌봄복지국 중장년노인과", "keywords": ["노인복지", "기초연금", "경로당지원", "노인일자리", "노인복지관"]},
    {"dept": "성평등가족국 저출생대응과", "keywords": ["인구정책", "저출생대응", "출산지원금", "다자녀정책", "첫만남이용권", "여성친화도시"]},
    {"dept": "성평등가족국 영유아보육과", "keywords": ["어린이집", "시립어린이집", "국공립어린이집", "보육료", "부모급여", "육아종합지원센터"]},
    {"dept": "성평등가족국 청년청소년과", "keywords": ["청년정책", "청년일자리", "청년지원센터", "청소년수련관", "학생동아리축제", "동아리축제", "청소년축제"]},
    {"dept": "농정해양국 농업정책과", "keywords": ["공익직불제", "농지관리", "농지진흥지역", "벼병해충방제", "후계농업인", "친환경농업"]},
    {"dept": "농정해양국 농식품유통과", "keywords": ["로컬푸드", "공공급식", "학교무상급식", "햇살드리", "수향미", "송산포도축제"]},
    {"dept": "농정해양국 축산정책과", "keywords": ["축산정책", "가축방역", "아프리카돼지열병", "조류인플루엔자", "구제역", "가축분뇨"]},
    {"dept": "농정해양국 해양수산과", "keywords": ["전곡항", "궁평항", "어항개발", "어선등록", "양식어업", "수산자원", "해양쓰레기"]},
    {"dept": "교통국 철도전략과", "keywords": ["광역철도망", "GTX", "신안산선", "동탄인덕원선", "서해선복선전철", "복합환승센터"]},
    {"dept": "교통국 대중교통과", "keywords": ["시내버스", "마을버스", "광역버스", "버스공영제", "공영버스", "택시요금", "수요응답형버스"]},
    {"dept": "교통국 주차물류과", "keywords": ["공영주차장", "거주자우선주차", "주차타워", "불법주정차", "화물차공영차고지"]},
    {"dept": "기업투자실 첨단산업과", "keywords": ["반도체클러스터", "미래모빌리티", "자율주행", "모빌리티", "MARS", "우주·모빌리티", "AX", "UAM", "인공지능포럼"]},
    {"dept": "기업투자실 기업지원과", "keywords": ["중소기업지원", "기업애로사항", "소공인지원", "육성자금", "수출지원", "화성산업진흥원"]},
    {"dept": "기업투자실 지역경제과", "keywords": ["지역화폐", "희망화성지역화폐", "소상공인지원", "전통시장활성화", "상점가육성", "물가안정"]},
    {"dept": "문화관광국 문화예술과", "keywords": ["문화재단", "화성예술의전당", "시립미술관", "동탄복합문화센터", "문화예술축제"]},
    {"dept": "문화관광국 관광진흥과", "keywords": ["지질공원", "지질공원한마당", "국가지질공원", "화성뱃놀이축제", "서해안관광단지", "제부도케이블카", "시티투어"]},
    {"dept": "교육체육국 교육지원과", "keywords": ["교육발전특구", "교육경비지원", "인재육성재단", "학교복합시설", "장학관"]},
    {"dept": "교육체육국 체육진흥과", "keywords": ["생활체육", "공공체육시설", "화성종합경기타운", "시민체육대회", "장애인체육"]},
    {"dept": "공원녹지사업소 공원조성과", "keywords": ["공원녹지기본계획", "도시공원조성", "우리꽃식물원", "마을정원"]},
    {"dept": "공원녹지사업소 보타닉가든추진단", "keywords": ["보타닉가든", "보타닉가든화성", "도심수목원", "사계절온실"]}
]


def clean_html(text):
    if not text:
        return ""
    unescaped = html.unescape(text)
    return re.sub(r"<[^>]+>", "", unescaped).strip()


def extract_media_name(link, originallink):
    target = originallink if originallink else link
    if "yna.co.kr" in target: return "연합뉴스"
    if "kyeongin.com" in target: return "경인일보"
    if "kgnews.co.kr" in target: return "경기일보"
    if "joongboo.com" in target: return "중부일보"
    if "newsis.com" in target: return "뉴시스"
    if "news1.kr" in target: return "뉴스1"
    if "kihoilbo.co.kr" in target: return "기호일보"
    if "etnews.com" in target: return "전자신문"
    if "sedaily.com" in target: return "서울경제"
    if "asiae.co.kr" in target: return "아시아경제"
    if "surprise-news.kr" in target or "sporbiz" in target: return "서프라이즈뉴스"
    return "언론사"


def parse_pub_date(date_str):
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        kst = timezone(timedelta(hours=9))
        return dt.astimezone(kst)
    except Exception:
        return datetime.now(timezone(timedelta(hours=9)))


def scrape_full_body(url):
    """국내 지역 언론사 CMS 대응 정밀 본문 스크래퍼"""
    if not url:
        return ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=4)
        if not res.ok:
            return ""
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")

        # 광고 및 불필요한 태그 제거
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "form"]):
            tag.decompose()

        # 주요 언론사 본문 컨테이너 탐색
        body_container = (
            soup.find("article", id="dic_area")
            or soup.find("div", id="dic_area")
            or soup.find("div", id="article-view-content-div")
            or soup.find("div", id="articleBody")
            or soup.find("div", class_="article-body")
            or soup.find("div", class_="article_body")
            or soup.find("div", id="news_body_area")
            or soup.find("div", class_="view-content")
            or soup.find("article")
        )

        if body_container:
            text = body_container.get_text(separator=" ", strip=True)
            if len(text) > 80:
                return text[:2000]

        # 문단 태그 폴백
        paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]
        if paras:
            return " ".join(paras)[:2000]
    except Exception:
        pass
    return ""


def rule_match_department(title, text):
    """1차 부서 매칭 (특례시 등 불필요 단어 배제)"""
    full_text = f"{title} {text}"
    best_dept = None
    max_score = 0

    for rule in DEPT_RULES:
        score = 0
        for kw in rule["keywords"]:
            if kw in title:
                score += 5
            elif kw in full_text:
                score += 1
        if score > max_score:
            max_score = score
            best_dept = rule["dept"]

    if max_score >= 1:
        return best_dept
    return "화성시 소관부서 확인중"


def analyze_with_gemini(client, title, content, rule_dept):
    """Gemini 3.8 Flash를 활용한 시정 관련성 판별 및 3줄 요약"""
    prompt = f"""당신은 화성시청 언론홍보 및 리스크 분석 수석 실무관입니다.
아래 기사를 정밀 분석하여 화성시 행정/시정과 관련된 기사인지 검증하고 JSON으로 출력하십시오.

[기사 제목]: {title}
[기사 내용]:
{content}
[1차 추천 소관부서]: {rule_dept}

[작업 지침]
1. is_hwaseong_news (화성시정 핵심 관련성 판별 - true 또는 false):
   - [반드시 true로 판별할 조건]:
     * 기사의 '주된 보도 대상(핵심 주제)'이 화성시(시청, 시장, 시의회, 시의장, 산하기관, 관내 사업소 등)의 고유 정책, 자체 추진 사업, 직접 주최/주관 행사, 관내 주요 현안 및 사건사고인 경우.
     * 기사 분량의 절반 이상이 화성시의 행정과 시민에 초점을 맞추고 있는 경우.

   - [반드시 false로 제외할 조건 - 엄격 적용]:
     * 타 지자체/타 기관 중심 기사의 단순 참석: 타 시·군·구(예: 용인시의회, 수원시, 평택시 등)나 경기도, 협의체 회의에서 화성시장·화성시의장 등이 단순 참석자/내빈으로 1~2줄 언급된 경우 (예: "용인시의회 정례회에 화성시의장 참석", "경기도 시장군수협의회 참석").
     * 광역/전국 지자체 단순 나열: 도청이나 중앙부처 기사에서 경기도 내 여러 시·군 목록 중 하나로 '화성시'가 곁가지로 나열된 경우.
     * 거시경제 및 단순 지명 통계: 전국 증시/환율, 거시경제 분석, 전국 아파트 분양/시세 통계 기사에서 '화성 사업장', '화성시 OO구' 등이 단순 예시나 수치로 1회 스쳐 지나간 경우.

2. category (is_hwaseong_news가 true일 때만 유효):
   - RISK: 시정 비판, 비리/의혹, 수사/감사 적발, 집단 민원 갈등, 대형 안전/환경 사고.
   - CULTURE: 행사, 축제, 대회, 전시, 포럼, 포상 수상.
   - POLICY: 일반 시정 홍보, 지원 사업, 협약(MOU), 도시 인프라 개발.

3. department: 기사 내용에 가장 부합하는 화성시 소관 실·과명 (기사와 무관하면 "해당없음").

4. bullets: 화성시 행정과 관련된 구체적 사실 중심의 3줄 핵심 요약 (각 줄은 '- '로 시작).

[출력 JSON 형식]:
{{
  "is_hwaseong_news": true | false,
  "category": "POLICY" | "CULTURE" | "RISK",
  "department": "소관부서명",
  "bullets": [
    "- 첫 번째 핵심 요약",
    "- 두 번째 핵심 요약",
    "- 세 번째 핵심 요약"
  ]
}}
"""
    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        if response and response.text:
            data = json.loads(response.text.strip())
            is_valid = data.get("is_hwaseong_news", True)
            return (
                is_valid,
                data.get("category", "POLICY"),
                data.get("department", rule_dept),
                data.get("bullets", [])[:3]
            )
    except Exception as e:
        print(f"Gemini 호출 에러 ({title[:20]}): {e}")

    # Fallback
    return True, "POLICY", rule_dept, [
        f"- {title}",
        f"- {content[:120]}...",
        "- 상세 내용은 기사 원문을 확인하시기 바랍니다."
    ]


def fetch_news():
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("네이버 API 인증 정보가 누락되었습니다.")
        return []

    enc_query = urllib.parse.quote("화성시")
    url = f"https://naverapihub.apigw.ntruss.com/search/v1/news?query={enc_query}&display=60&start=1&sort=date&format=json"
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_CLIENT_ID.strip(),
        "X-NCP-APIGW-API-KEY": NAVER_CLIENT_SECRET.strip(),
        "User-Agent": "Mozilla/5.0"
    }

    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.ok:
            return res.json().get("items", [])
    except Exception as e:
        print(f"네이버 수집 에러: {e}")
    return []


def main():
    print("화성시 뉴스 정밀 수집 및 Gemini 분석 시작...")
    if not GEMINI_API_KEY:
        print("경고: GEMINI_API_KEY가 등록되지 않았습니다.")
        return

    client = genai.Client(api_key=GEMINI_API_KEY.strip())
    raw_items = fetch_news()
    if not raw_items:
        print("수집된 뉴스가 없습니다.")
        return

    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    today_date = now_kst.date()
    yesterday_date = today_date - timedelta(days=1)

    processed_articles = []
    seen_titles = set()

    for item in raw_items:
        pub_dt = parse_pub_date(item.get("pubDate", ""))
        item_date = pub_dt.date()

        if item_date not in (today_date, yesterday_date):
            continue

        title = clean_html(item.get("title", ""))
        desc = clean_html(item.get("description", ""))
        link = item.get("originallink", "") or item.get("link", "")
        media = extract_media_name(item.get("link", ""), item.get("originallink", ""))

        # 중복 제목 단순 스킵
        core_title = re.sub(r"[^\w]", "", title)[:18]
        if core_title in seen_titles:
            continue
        seen_titles.add(core_title)

        # 1. 기사 본문 추출 (실패 시 description 대체)
        scraped_text = scrape_full_body(link)
        article_content = scraped_text if len(scraped_text) > 80 else desc

        # 2. 1차 부서 매칭
        rule_dept = rule_match_department(title, article_content)

        # 3. Gemini 실무 요약 및 판별
        print(f"분석 중: {title[:25]}...")
        is_valid, cat, dept, bullets = analyze_with_gemini(client, title, article_content, rule_dept)

        # 화성시정과 무관한 전국 경제/단순 지명 언급 기사는 자동 제외
        if not is_valid:
            print(f"   -> [제외] 화성시정 무관 기사 필터링: {title[:20]}")
            continue

        is_today = (item_date == today_date)
        time_label = f"오늘 {pub_dt.strftime('%H:%M')}" if is_today else f"어제 {pub_dt.strftime('%H:%M')}"
        date_group = "TODAY" if is_today else "YESTERDAY"

        processed_articles.append({
            "title": title,
            "link": link,
            "media": media,
            "category": cat,
            "department": dept,
            "date_group": date_group,
            "time_label": time_label,
            "pub_timestamp": pub_dt.isoformat(),
            "bullets": bullets,
            "related_articles": []
        })

        if len(processed_articles) >= 25:
            break

    # 통계 집계
    now_str = now_kst.strftime("%Y.%m.%d. %H:%M")
    result_data = {
        "updated_at": now_str,
        "yesterday_label": yesterday_date.strftime("%m.%d"),
        "stats": {
            "total": len(processed_articles),
            "today_count": sum(1 for a in processed_articles if a["date_group"] == "TODAY"),
            "yesterday_count": sum(1 for a in processed_articles if a["date_group"] == "YESTERDAY"),
            "policy": sum(1 for a in processed_articles if a["category"] == "POLICY"),
            "culture": sum(1 for a in processed_articles if a["category"] == "CULTURE"),
            "risk": sum(1 for a in processed_articles if a["category"] == "RISK")
        },
        "articles": processed_articles
    }

    with open("news_data.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f">> 완료: 총 {len(processed_articles)}건 분석 및 news_data.json 저장 성공")


if __name__ == "__main__":
    main()
