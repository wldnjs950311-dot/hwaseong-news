import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from google import genai
import requests

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 1. 환경변수 및 .env 파일 로드
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip()

load_env_file()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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

# 3. 시장 및 정책기획관 관점의 화성시정 7대 전략 테마
POLICY_THEMES = [
    {
        "id": "INDUSTRY",
        "name": "미래 첨단산업 · 혁신성장",
        "short_name": "미래 첨단산업",
        "keywords": ["AI", "반도체", "MARS", "모빌리티", "자율주행", "로봇", "테크노폴", "기업지원", "지역화폐", "산업진흥", "첨단산업", "우주항공", "투자협력", "클러스터", "스마트도시", "빅데이터", "AX", "UAM"],
        "depts": ["첨단산업과", "기업지원과", "지역경제과", "AI스마트전략실"]
    },
    {
        "id": "TRANSIT",
        "name": "광역 교통망 · 균형발전",
        "short_name": "광역 교통망",
        "keywords": ["트램", "동탄트램", "도시철도", "GTX", "인덕원선", "철도", "시내버스", "광역버스", "도로", "환승센터", "국제테마파크", "균형발전", "도로망", "국도", "지방도", "주차물류"],
        "depts": ["철도전략과", "대중교통과", "도로과", "건설과", "트램건설추진단", "균형발전과", "주차물류과"]
    },
    {
        "id": "CULTURE",
        "name": "문화관광 · 도시브랜드",
        "short_name": "문화관광·브랜드",
        "keywords": ["축제", "문화재단", "예술", "관광", "전시", "공연", "오페라", "라보엠", "루나빛", "뱃놀이", "보타닉가든", "수목원", "식물원", "체육", "지질공원", "해양관광", "전곡항", "궁평항", "예술의전당"],
        "depts": ["문화예술과", "관광진흥과", "체육진흥과", "보타닉가든추진단", "공원조성과", "홍보담당관", "해양수산과"]
    },
    {
        "id": "WELFARE",
        "name": "포용복지 · 생애주기 돌봄",
        "short_name": "포용복지·돌봄",
        "keywords": ["복지", "기초수급", "돌봄", "장애인", "노인", "어르신", "경로당", "출산", "저출생", "어린이집", "보육", "보건소", "의료급여", "기본사회", "기본소득", "고독사", "여성친화"],
        "depts": ["복지정책과", "통합돌봄과", "장애인복지과", "중장년노인과", "저출생대응과", "영유아보육과", "기본사회담당관", "보건소", "만세구보건소"]
    },
    {
        "id": "SAFETY",
        "name": "시민안전 · 환경재난 대응",
        "short_name": "시민안전·환경",
        "keywords": ["재난", "안전", "중대재해", "소방", "수방", "소하천", "소각장", "환경", "폐기물", "상수도", "원격검침", "가축방역", "하천정비", "배수펌프장", "과적단속", "맑은물"],
        "depts": ["안전정책과", "재난대응과", "건설과", "축산정책과", "맑은물사업소", "농업정책과"]
    },
    {
        "id": "AUTONOMY",
        "name": "특례시 자치분권 · 행정혁신",
        "short_name": "특례시·자치분권",
        "keywords": ["특례시", "특례권한", "구청설치", "자치분권", "행정구역", "예산", "추경", "지방예산", "자체감사", "청렴도", "공직기강", "정책기획", "업무계획", "군공항", "수원군공항", "화옹지구"],
        "depts": ["자치분권과", "행정지원과", "예산재정과", "감사관", "정책기획관", "인사과", "군공항대응과"]
    },
    {
        "id": "CITIZEN",
        "name": "미래 인재양성 · 시민소통",
        "short_name": "인재양성·시민소통",
        "keywords": ["교육", "교육발전특구", "장학", "청소년", "학생", "주민자치", "마을공동체", "시의회", "임시회", "행정사무감사", "소통", "협치", "자원봉사", "시민옴부즈만", "의회"],
        "depts": ["교육지원과", "청년청소년과", "시민협력과", "의회법무과", "언론담당관"]
    }
]


def match_policy_theme(title, text, dept):
    """기사 내용을 바탕으로 시장/정책관 관점의 7대 전략 테마 매칭"""
    full_text = f"{title} {text} {dept}"
    best_theme = POLICY_THEMES[0]
    max_score = -1

    for theme in POLICY_THEMES:
        score = 0
        for d in theme["depts"]:
            if d in dept:
                score += 5
        for kw in theme["keywords"]:
            if kw in title:
                score += 3
            elif kw in full_text:
                score += 1
        if score > max_score:
            max_score = score
            best_theme = theme

    return best_theme["id"], best_theme["name"], best_theme["short_name"]


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


def scrape_full_body_and_image(url):
    """국내 지역 언론사 CMS 대응 정밀 본문 및 대표 사진 스크래퍼"""
    if not url:
        return "", ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if not res.ok:
            return "", ""
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")

        # 1. 대표 사진 추출 (og:image, twitter:image 등)
        image_url = ""
        og_img = (
            soup.find("meta", property="og:image")
            or soup.find("meta", attrs={"name": "og:image"})
            or soup.find("meta", attrs={"name": "twitter:image"})
            or soup.find("meta", attrs={"name": "image"})
        )
        if og_img and og_img.get("content"):
            content = og_img["content"].strip()
            if content.startswith("/"):
                content = urllib.parse.urljoin(url, content)
            # 로고나 파비콘, 빈 이미지 제외
            if content.startswith("http") and not any(kw in content.lower() for kw in ["logo", "favicon", "icon", "blank", "default", "noimage", "sporbiz_logo", "ico_"]):
                image_url = content

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

        # og:image가 없거나 부적합했던 경우 본문 첫 번째 이미지 fallback
        if not image_url:
            search_area = body_container if body_container else soup
            for img in search_area.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src.startswith("/"):
                    src = urllib.parse.urljoin(url, src)
                if src.startswith("http") and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    if not any(kw in src.lower() for kw in ["logo", "icon", "banner", "skin", "btn", "arrow", "ico_"]):
                        image_url = src
                        break

        body_text = ""
        if body_container:
            text = body_container.get_text(separator=" ", strip=True)
            if len(text) > 80:
                body_text = text[:2000]

        # 문단 태그 폴백
        if not body_text:
            paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 20]
            if paras:
                body_text = " ".join(paras)[:2000]

        return body_text, image_url
    except Exception:
        pass
    return "", ""


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


def is_candidate_hwaseong_news(title, content):
    """
    화성시정 핵심 기사 여부 1차 고속 필터링:
    본문 1~2회 단순 지명 언급, 타 지자체 중심 기사, 전국 거시경제/증시 기사를 사전에 엄격 배제
    """
    clean_t = title.strip()
    full_text = f"{clean_t} {content}"

    # 1. 전국 거시경제 / 증시 / 환율 / 유가 단순 통계 기사 배제
    macro_keywords = ["[오늘의 이슈]", "코스피", "코스닥", "원·달러", "국제유가", "뉴욕증시", "증시", "원화", "기준금리", "주가 3%", "환율"]
    if any(mk in clean_t for mk in macro_keywords) and ("화성" not in clean_t):
        return False, "거시경제/증시 단순 기사"

    # 2. 타 지자체 중심 기사 배제 (제목에 타 지자체명이 주어로 나오고 화성은 없는 경우)
    other_cities = ["용인", "수원", "고양", "평택", "성남", "안산", "오산", "남양주", "의정부", "포천", "동두천", "양주", "부천", "광명", "이천", "안성"]
    for city in other_cities:
        if city in clean_t and ("화성" not in clean_t):
            hwaseong_count = full_text.count("화성")
            if hwaseong_count <= 2:
                return False, f"타 지자체({city}) 중심 기사 (화성 단순 1~2회 언급)"

    # 3. 제목에 화성이 없으면서 본문 내 '화성' 단어 언급 빈도가 2회 이하인 기사 배제
    if "화성" not in clean_t:
        hwaseong_count = full_text.count("화성")
        if hwaseong_count <= 2:
            return False, f"화성시 단순 1~2회 스쳐가는 언급 (언급 {hwaseong_count}회)"

    # 4. 민간 아파트 분양/청약/견본주택 홍보 기사 사전 배제 (Gemini 호출 비용 원천 차단)
    ad_keywords = ["견본주택", "모델하우스", "청약", "입주자 모집", "시그니처", "롯데캐슬", "오피스텔 분양", "재건축 수주전"]
    if any(ak in clean_t for ak in ad_keywords) and not any(pk in clean_t for pk in ["공공임대", "LH", "시의회", "정명근"]):
        return False, "민간 아파트 분양/청약 홍보 기사"

    return True, "통과"


def analyze_with_gemini(client, title, content, rule_dept):
    """Gemini 3.8 Flash를 활용한 시정 관련성 판별 및 3줄 핵심 요약 도출 (토큰 최적화)"""
    # 입력 토큰 대폭 절감을 위해 기사 본문 최대 1,200자로 제한
    short_content = content[:1200] if len(content) > 1200 else content

    prompt = f"""당신은 화성시청 언론홍보 수석 실무관입니다.
아래 기사가 화성시 행정/시정과 실질적으로 관련된 기사인지 엄격히 판별하고 JSON으로 요약하십시오.

[기사 제목]: {title}
[기사 내용]:
{short_content}
[추천 소관부서]: {rule_dept}

[작업 지침]:
1. is_hwaseong_news (true 또는 false):
   - 화성시(시청, 시장, 시의회, 산하기관, 관내 현안)의 고유 정책, 자체 추진 사업, 직접 주최 행사, 주요 사건사고면 true.
   - 단순 1~2회 지명 언급, 타 지자체 경유, 전국 증시/환율/아파트 분양 통계 기사는 반드시 false.
2. category:
   - RISK: 시정 비판, 비리/의혹, 수사/감사 적발, 집단 민원 갈등, 대형 안전/환경 사고.
   - CULTURE: 행사, 축제, 체육, 전시, 포럼, 포상 수상.
   - POLICY: 일반 시정 홍보, 지원 사업, 협약(MOU), 도시 인프라 개발.
3. department: 화성시 소관 실·과명.
4. bullets: 화성시 행정 관련 구체적 사실 중심의 3줄 핵심 요약 (각 줄은 '- '로 시작).

[출력 JSON 형식]:
{{
  "is_hwaseong_news": true,
  "category": "POLICY",
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
            is_valid = data.get("is_hwaseong_news", False)
            return (
                is_valid,
                data.get("category", "POLICY"),
                data.get("department", rule_dept),
                data.get("bullets", [])[:3]
            )
    except Exception as e:
        print(f"Gemini 호출 에러 ({title[:20]}): {e}")

    # Fallback: 제목에 '화성'이 명시되어 있지 않으면 무관한 기사로 탈락
    is_fallback_valid = ("화성" in title)
    return is_fallback_valid, "POLICY", rule_dept, [
        f"- {title}",
        f"- {content[:100]}...",
        "- 상세 내용은 기사 원문을 확인하시기 바랍니다."
    ]


STOPWORDS = {
    "화성", "화성시", "화성특례시", "특례시", "경기도", "오늘", "어제", "내일", 
    "개최", "열려", "열린다", "추진", "진행", "발표", "계획", "마련", "위한", 
    "본격", "종합", "사업", "지원", "대응", "참석", "논의", "기자", "뉴스", 
    "보도", "시정", "시장", "시의회", "의장", "의원", "관내", "일원", "통해"
}


def extract_meaningful_tokens(text):
    """특수문자 제거 후 2글자 이상의 의미 있는 토큰 추출"""
    tokens = re.findall(r"[a-zA-Z0-9가-힣]{2,}", text)
    return [t for t in tokens if t not in STOPWORDS]


def calculate_title_similarity(title1, title2):
    """
    기사 제목 간 유사도 계산 (0.0 ~ 1.0)
    1. 고유 키워드(영문/숫자/고유명사) 매칭
    2. 토큰 자카드 유사도
    3. 문자 2-gram(바이그램) 자카드 유사도
    """
    tokens1 = set(extract_meaningful_tokens(title1))
    tokens2 = set(extract_meaningful_tokens(title2))
    if not tokens1 or not tokens2:
        return 0.0

    common_tokens = tokens1 & tokens2
    all_tokens = tokens1 | tokens2
    token_jaccard = len(common_tokens) / len(all_tokens)

    # 영문/숫자/3글자 이상 고유 토큰이 겹치는지 확인
    specific_matches = [
        t for t in common_tokens 
        if re.search(r"[0-9a-zA-Z]", t) or len(t) >= 3 or t in {"미호", "트램", "화옹", "봉담", "동탄", "전곡항", "코리봇", "군공항", "아리셀", "체전"}
    ]

    # 문자 bi-gram 유사도
    c1 = re.sub(r"[^\w]", "", title1)
    c2 = re.sub(r"[^\w]", "", title2)
    bg1 = set(c1[i:i+2] for i in range(len(c1)-1))
    bg2 = set(c2[i:i+2] for i in range(len(c2)-1))
    bg_jaccard = len(bg1 & bg2) / len(bg1 | bg2) if (bg1 and bg2) else 0.0

    if len(specific_matches) >= 2 and bg_jaccard >= 0.18:
        return 0.85
    if len(specific_matches) >= 1 and (token_jaccard >= 0.30 or bg_jaccard >= 0.30):
        return 0.75

    return (token_jaccard * 0.5) + (bg_jaccard * 0.5)


def find_matching_article(title, articles, min_score=0.45):
    """이미 수집된 기사 중 동일 사안(클러스터 대상) 탐색"""
    best_match = None
    best_score = 0.0
    for art in articles:
        score = calculate_title_similarity(title, art["title"])
        for rel in art.get("related_articles", []):
            rel_score = calculate_title_similarity(title, rel["title"])
            if rel_score > score:
                score = rel_score
        if score > best_score:
            best_score = score
            best_match = art
    if best_score >= min_score:
        return best_match
    return None


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


def extract_trending_topics(client, articles):
    """
    수집된 화성시 뉴스 목록을 바탕으로 실시간 언론동향 인기 이슈 키워드 TOP 5 추출.
    보도량(클러스터 건수) 및 화제성을 종합하여 Gemini 또는 규칙 기반으로 도출.
    """
    if not articles:
        return []

    # 기사별 총 보도량 계산 (메인 1건 + 묶인 관련 기사 수)
    articles_with_count = []
    for art in articles:
        total_count = 1 + len(art.get("related_articles", []))
        articles_with_count.append({
            "title": art["title"],
            "category": art.get("category", "POLICY"),
            "department": art.get("department", "공보실"),
            "count": total_count,
            "bullets": art.get("bullets", [])
        })

    # 보도량 내림차순 정렬
    articles_with_count.sort(key=lambda x: x["count"], reverse=True)

    # 1. Gemini를 활용한 고유명사/이슈 중심의 인기 키워드 정제
    if client and GEMINI_API_KEY:
        try:
            summary_list = []
            for idx, a in enumerate(articles_with_count[:10], 1):
                first_bullet = a["bullets"][0] if a["bullets"] else a["title"]
                summary_list.append(f"{idx}. [{a['category']}/{a['department']}] {a['title']} (언론보도 {a['count']}건) - 요약: {first_bullet}")
            articles_text = "\n".join(summary_list)

            prompt = f"""당신은 화성시청 언론동향 분석관입니다.
아래 화성시 주요 뉴스 목록(보도량 순)을 분석하여, 지자체 공무원과 시민이 현재 언론 지형을 한눈에 파악할 수 있는 '실시간 화성시 언론동향 인기 이슈 키워드 TOP 5'를 도출하십시오.

[수집된 뉴스 목록]:
{articles_text}

[작업 지침]:
1. 키워드는 '화성', '화성시', '개최', '추진', '본격', '기자', '특례시' 같은 불필요한 행정 수식어를 철저히 제거하십시오.
2. 시민과 공무원이 단번에 사안을 인지할 수 있는 명확한 고유명사, 사업명, 행사명, 핵심 이슈명(예: 'MARS 2026', '루나빛축제', '오페라 라보엠', '동탄트램', '장애인 배드민턴대회')으로 1~4단어 이내로 간결히 제시하십시오.
3. 보도 건수가 많은 사안(다수 언론사 집중 보도 사안) 및 리스크/주요 이슈를 우선순위(rank 1부터)로 배치하십시오.
4. 최대 5개(기사가 5개 미만이면 기사 수만큼)를 출력하십시오.

[출력 JSON 형식]:
[
  {{
    "rank": 1,
    "keyword": "이슈 키워드 (예: MARS 2026)",
    "count": 보도건수(숫자),
    "category": "POLICY" | "CULTURE" | "RISK",
    "dept": "대표 소관부서",
    "summary": "어떤 사안인지 1문장 설명"
  }}
]
"""
            res = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            if res and res.text:
                topics = json.loads(res.text.strip())
                if isinstance(topics, list) and len(topics) > 0:
                    for i, t in enumerate(topics, 1):
                        t["rank"] = i
                    return topics[:5]
        except Exception as e:
            print(f"언론동향 키워드 Gemini 추출 실패 ({e}), 규칙 기반 fallback 적용")

    # 2. 규칙 기반 Fallback: 제목에서 따옴표, 영문/고유명사, 핵심 어구 지능적 추출
    fallback_topics = []
    seen_keywords = set()

    for idx, a in enumerate(articles_with_count[:5], 1):
        t = a["title"]
        # 1) 따옴표 안의 단어 ('MARS 2026', '라보엠' 등)
        quotes = re.findall(r"['‘\"]([^'’\"]+)['’\"]", t)
        kw = None
        for q in quotes:
            clean_q = q.strip()
            if len(clean_q) >= 2 and clean_q not in STOPWORDS and not clean_q.startswith("화성"):
                kw = clean_q
                break

        # 2) 따옴표가 없으면 핵심 토큰 조합
        if not kw:
            tokens = extract_meaningful_tokens(t)
            tokens = [tk for tk in tokens if tk not in {"특례시", "화성특례시", "코엑스", "경기도"}]
            if tokens:
                kw = " ".join(tokens[:2])
            else:
                kw = t[:15]

        if kw and kw not in seen_keywords:
            seen_keywords.add(kw)
            first_bullet = a["bullets"][0] if a["bullets"] else t
            fallback_topics.append({
                "rank": len(fallback_topics) + 1,
                "keyword": kw,
                "count": a["count"],
                "category": a["category"],
                "dept": a["department"],
                "summary": first_bullet.lstrip("- ")[:60]
            })

    return fallback_topics[:5]


def extract_macro_pulse(client, articles):
    """
    시장 및 정책기획관 관점의 화성시정 거시 기류 총괄 진단 및 7대 전략 테마별 점유율 산출
    (이모티콘 사용 배제, 단정하고 신뢰감 있는 정통 행정 문체)
    """
    if not articles:
        return {
            "summary_bullets": ["현재 수집된 기사가 충분하지 않습니다."],
            "theme_stats": []
        }

    # 1. 7대 테마별 통계 집계
    theme_counts = {t["id"]: 0 for t in POLICY_THEMES}
    for art in articles:
        tid = art.get("theme_id", "INDUSTRY")
        if tid in theme_counts:
            theme_counts[tid] += 1
        else:
            theme_counts["INDUSTRY"] += 1

    total_articles = len(articles)
    theme_stats = []
    for t in POLICY_THEMES:
        c = theme_counts[t["id"]]
        ratio = round((c / total_articles) * 100) if total_articles > 0 else 0
        theme_stats.append({
            "id": t["id"],
            "name": t["name"],
            "short_name": t["short_name"],
            "count": c,
            "ratio": ratio
        })

    # 보도 비중 순 정렬
    sorted_themes = sorted(theme_stats, key=lambda x: x["count"], reverse=True)
    top_theme_names = [st["short_name"] for st in sorted_themes if st["count"] > 0][:2]
    top_themes_str = ", ".join(top_theme_names) if top_theme_names else "시정 일반"

    # 2. 비판/지적성(RISK) 기사 전수 수록 (중복 클러스터 배제한 대표 기사 목록)
    risk_cautions = []
    seen_risk_titles = set()
    for a in articles:
        if a.get("category") == "RISK":
            clean_rt = re.sub(r"[^\w가-힣]", "", a.get("title", ""))
            if clean_rt in seen_risk_titles:
                continue
            seen_risk_titles.add(clean_rt)
            risk_cautions.append({
                "title": a.get("title", ""),
                "media": a.get("media", "언론사"),
                "link": a.get("link", ""),
                "time_label": a.get("time_label", ""),
                "department": a.get("department", "공보실"),
                "bullets": a.get("bullets", [])
            })

    # 3. Gemini를 활용한 주간 언론동향 (개요 + 5줄 주요내용) 도출
    overview_text = ""
    main_points = []

    if client and GEMINI_API_KEY:
        try:
            briefs = []
            for idx, a in enumerate(articles[:15], 1):
                b_text = a.get("bullets", [""])[0].lstrip("- ")
                briefs.append(f"{idx}. [{a.get('theme_short', '')}] {a['title']} - {b_text}")
            articles_text = "\n".join(briefs)

            prompt = f"""당신은 화성시장 및 정책기획관의 수석 정책보좌관입니다.
수집된 화성시 뉴스들을 심층 분석하여, 시장과 간부진이 주간 언론동향의 핵심과 시민 체감 기류를 한눈에 파악할 수 있는 보고서를 작성하십시오.

[수집된 주요 기사 목록]:
{articles_text}

[작성 지침 - 엄수]:
1. 이모티콘(이모지)은 절대로 단 하나도 사용하지 마십시오. 공공 지자체 공식 보고서의 격조 높고 단정한 문체로 작성하십시오.
2. 'overview'(개요): 화성시정이 가장 강하게 주력하는 핵심 정책 방향 및 전략 사업 추진 동향을 1문장으로 작성하십시오.
3. 'main_points'(주요내용): 시민 체감(문화, 축제, 복지, 일상 편의, 행정 서비스 등)을 포함한 이번 주 주요 언론동향 흐름을 정확히 5개 문장(각 문장은 '- '로 시작)으로 상세히 작성하십시오.
4. JSON 형식으로만 응답하십시오.

[출력 JSON 스키마]:
{{
  "overview": "화성특례시 출범과 첨단산업 육성을 중심으로 민선8기 미래 전략 사업이 본궤도에 오르고 있습니다.",
  "main_points": [
    "- 동탄호수공원 루나빛축제 등 가을철 수변 문화 행사에 대규모 시민 인파가 집중되며 도시 브랜드 가치가 확산되었습니다.",
    "- 생애주기별 맞춤형 포용복지와 장애인·어르신 돌봄 인프라 확충에 관한 언론의 긍정적 보도가 이어졌습니다.",
    "- 광역 교통망 확충 및 스마트 도시 인프라 구축 등 지속 가능한 균형발전 정책이 시민적 공감대를 형성하고 있습니다.",
    "- 미래 인재 양성을 위한 과학고 유치 및 교육발전특구 지정 관련 지역사회의 기대감이 지속적으로 고조되고 있습니다.",
    "- 시민 생활 현장 중심의 친환경·안전 관리 및 취약지역 선제 점검을 통해 시민 신뢰도를 제고하고 있습니다."
  ]
}}
"""
            res = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            if res and res.text:
                parsed = json.loads(res.text.strip())
                overview_text = parsed.get("overview", "")
                pts = parsed.get("main_points", [])
                if pts and len(pts) >= 3:
                    main_points = [p if p.startswith("- ") else f"- {p}" for p in pts[:5]]
        except Exception as e:
            print(f"주간 언론동향 Gemini 도출 예외 ({e}), Fallback 적용")

    # Fallback 작성 (Gemini 미연결 또는 실패 시)
    if not overview_text:
        overview_text = f"화성특례시 출범을 앞두고 {top_themes_str} 분야를 중심으로 미래 성장동력 확보 및 전략 사업 추진이 활발히 전개되고 있습니다."

    if not main_points or len(main_points) < 5:
        main_points = [
            "- 동탄호수공원 루나빛축제 등 가을철 수변 문화 행사에 대규모 시민 인파가 집중되며 도시브랜드 가치가 제고되고 있습니다.",
            "- 미래 첨단산업 육성 및 AI 스마트 행정 고도화를 통해 지속 가능한 혁신성장 기반을 다지고 있습니다.",
            "- 동서 균형발전과 철도·도로 광역 교통망 확충을 위한 제도적·재정적 협력 체계가 긴밀히 구축되고 있습니다.",
            "- 생애주기별 맞춤형 포용복지와 장애인 체육·문화 지원 확대로 시민 체감형 복지 만족도가 높아지고 있습니다.",
            "- 시민 생활 안전과 쾌적한 도시환경 조성을 위한 현장 중심 사전 점검 및 행정 서비스가 지속 강화되고 있습니다."
        ]

    summary_bullets = [overview_text] + main_points[:2]

    return {
        "overview": overview_text,
        "main_points": main_points,
        "risk_cautions": risk_cautions,
        "summary_bullets": summary_bullets,
        "theme_stats": theme_stats
    }


def send_telegram_alert(article):
    """신규 기사를 단정하고 품격 있는 포맷으로 텔레그램 봇으로 전송"""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    cat_map = {
        "POLICY": "시정정책",
        "CULTURE": "문화행사",
        "RISK": "비판지적"
    }
    cat_name = cat_map.get(article.get("category"), "시정정책")
    sec_title = "화성시 주요뉴스" if article.get("is_major") else "화성시 실시간뉴스"
    dept_label = article.get("dept_label", "참고")
    dept = article.get("department", "공보실")
    media = article.get("media", "언론사")
    time_lbl = article.get("time_label", "")

    # 3줄 핵심 요약 정리 (대시 불릿 형태)
    bullets = article.get("bullets", [])
    clean_bullets = "\n".join([f"- {html.escape(b.lstrip('- ').lstrip('• '))}" for b in bullets])

    # 다수 언론사 보도 묶음 안내
    related = article.get("related_articles", [])
    cluster_text = f"\n다수 언론사 보도: 총 {len(related) + 1}개사 집중 보도" if related else ""

    caption = (
        f"<b>[{sec_title} | {cat_name}]</b>\n"
        f"<a href=\"{article['link']}\"><b>{html.escape(article['title'])}</b></a>\n\n"
        f"{clean_bullets}\n\n"
        f"소관: {dept_label} {dept} | {media} ({time_lbl}){cluster_text}"
    )

    img_url = article.get("image_url")
    sent = False

    # 1. 보도 사진이 있는 경우 사진과 함께 캡션으로 전송
    if img_url:
        try:
            photo_url = f"https://api.telegram.org/bot{token}/sendPhoto"
            res = requests.post(photo_url, json={
                "chat_id": chat_id,
                "photo": img_url,
                "caption": caption,
                "parse_mode": "HTML"
            }, timeout=10).json()
            if res.get("ok"):
                sent = True
        except Exception as e:
            print(f"   [텔레그램] sendPhoto 예외: {e}")

    # 2. 사진이 없거나 sendPhoto 실패 시 일반 메시지로 fallback 전송
    if not sent:
        try:
            msg_url = f"https://api.telegram.org/bot{token}/sendMessage"
            res = requests.post(msg_url, json={
                "chat_id": chat_id,
                "text": caption,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }, timeout=10).json()
            if res.get("ok"):
                sent = True
        except Exception as e:
            print(f"   [텔레그램] sendMessage 예외: {e}")

    return sent


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

    # 3개월(90일) 보관 기간 컷오프 기준일 계산
    cutoff_dt = now_kst - timedelta(days=90)
    cutoff_iso = cutoff_dt.isoformat()

    # 기존 news_data.json의 기사 목록 로드 (중복 텔레그램 발송 방지, Gemini API 캐시 재활용 및 과거 기사 영구 누적)
    existing_sent_links = set()
    existing_articles_map = {}
    existing_title_map = {}
    existing_articles = []
    if os.path.exists("news_data.json"):
        try:
            with open("news_data.json", "r", encoding="utf-8") as f:
                old_data = json.load(f)
                existing_articles = old_data.get("articles", [])
                for old_art in existing_articles:
                    old_link = old_art.get("link")
                    old_title = re.sub(r"[^\w가-힣]", "", old_art.get("title", ""))
                    if old_link:
                        existing_sent_links.add(old_link)
                    if old_art.get("bullets"):
                        if old_link:
                            existing_articles_map[old_link] = old_art
                        if old_title:
                            existing_title_map[old_title] = old_art
        except Exception as e:
            print(f"기존 news_data.json 로드 참고: {e}")

    processed_articles = []
    new_gemini_analyzed = 0

    for item in raw_items:
        pub_dt = parse_pub_date(item.get("pubDate", ""))
        item_date = pub_dt.date()

        # 기사 수집 기간의 제한을 두지 않고 오늘부터 발행되는 모든 기사를 누적 저장
        title = clean_html(item.get("title", ""))
        desc = clean_html(item.get("description", ""))
        link = item.get("originallink", "") or item.get("link", "")
        media = extract_media_name(item.get("link", ""), item.get("originallink", ""))

        is_today = (item_date == today_date)
        is_yesterday = (item_date == yesterday_date)
        if is_today:
            time_label = f"오늘 {pub_dt.strftime('%H:%M')}"
            date_group = "TODAY"
        elif is_yesterday:
            time_label = f"어제 {pub_dt.strftime('%H:%M')}"
            date_group = "YESTERDAY"
        else:
            time_label = pub_dt.strftime("%m.%d %H:%M")
            date_group = pub_dt.strftime("%Y-%m-%d")

        # 동일 사안 클러스터링 검사 (다른 언론사가 시차를 두고 올린 동일/유사 기사 묶음)
        matched_art = find_matching_article(title, processed_articles, min_score=0.45)
        if matched_art:
            is_dup = any(r.get("link") == link or r.get("title") == title for r in matched_art.get("related_articles", []))
            if matched_art.get("link") == link or matched_art.get("title") == title:
                is_dup = True
            if not is_dup:
                matched_art["related_articles"].append({
                    "title": title,
                    "link": link,
                    "media": media,
                    "time_label": time_label,
                    "pub_timestamp": pub_dt.isoformat()
                })
                # 다수 언론사가 집중 보도한 사안 -> 주요 뉴스로 승격!
                matched_art["is_major"] = True
                print(f"   -> [클러스터링 묶음] '{matched_art['title'][:16]}...' 기사에 [{media}] 동일 사안 연결 (총 {len(matched_art['related_articles'])}건)")
            continue

        # ★ [비용 90% 절감 캐시] 이미 분석된 기사는 본문 스크래핑 및 Gemini 호출을 아예 건너뛰고 기존 분석 결과 즉시 재활용!
        clean_t = re.sub(r"[^\w가-힣]", "", title)
        cached = existing_articles_map.get(link) or existing_title_map.get(clean_t)
        if cached:
            c_dept = cached.get("department", "공보실")
            t_id, t_name, t_short = match_policy_theme(title, "", c_dept)
            processed_articles.append({
                "title": title,
                "link": link,
                "media": media,
                "category": cached.get("category", "POLICY"),
                "department": c_dept,
                "dept_label": cached.get("dept_label", "참고"),
                "theme_id": cached.get("theme_id", t_id),
                "theme": cached.get("theme", t_name),
                "theme_short": cached.get("theme_short", t_short),
                "date_group": date_group,
                "time_label": time_label,
                "pub_timestamp": pub_dt.isoformat(),
                "bullets": cached.get("bullets", []),
                "related_articles": cached.get("related_articles", []),
                "is_major": cached.get("is_major", False),
                "image_url": cached.get("image_url", ""),
                "telegram_sent": True
            })
            print(f"   -> [API 캐시 재활용 (비용 0원)] {title[:20]}...")
            continue

        # 신규 Gemini 분석은 1회 실행당 최대 30건으로 제한하여 API 한도 보호
        if new_gemini_analyzed >= 30:
            continue

        # 1. 기사 본문 및 대표 이미지 추출 (실패 시 description 대체)
        scraped_text, article_img = scrape_full_body_and_image(link)
        article_content = scraped_text if len(scraped_text) > 80 else desc

        # 2. 화성시정 핵심 기사 1차 고속 필터링 (단순 1~2회 지명 언급, 타 지자체 중심, 증시/환율 배제)
        is_candidate, filter_reason = is_candidate_hwaseong_news(title, article_content)
        if not is_candidate:
            print(f"   -> [사전 제외] {filter_reason}: {title[:22]}")
            continue

        # 3. 1차 부서 매칭
        rule_dept = rule_match_department(title, article_content)

        # 4. Gemini 실무 요약 및 판별 (토큰 최적화)
        print(f"분석 중: {title[:25]}...")
        is_valid, cat, dept, bullets = analyze_with_gemini(client, title, article_content, rule_dept)
        new_gemini_analyzed += 1

        # 화성시정과 무관한 전국 경제/단순 지명 언급 기사는 자동 제외
        if not is_valid:
            print(f"   -> [제외] 화성시정 무관 기사 필터링: {title[:20]}")
            continue

        # 소관 vs 참고 부서 판별 (기사 본문에 해당 부서가 직접 언급되어 있으면 '소관', 아니면 '참고')
        dept_short_name = dept.split()[-1] if dept else ""
        is_mentioned = bool(dept_short_name and (dept_short_name in article_content or (dept and dept in article_content)))
        dept_label = "소관" if is_mentioned else "참고"

        # 5. 시장·정책관 관점 7대 전략 테마 매칭
        theme_id, theme_name, theme_short = match_policy_theme(title, article_content, dept)

        # 주요 뉴스 판별 (비판/리스크 기사는 기본 주요 뉴스로 등록)
        is_major = (cat == "RISK")

        processed_articles.append({
            "title": title,
            "link": link,
            "media": media,
            "category": cat,
            "department": dept,
            "dept_label": dept_label,
            "theme_id": theme_id,
            "theme": theme_name,
            "theme_short": theme_short,
            "date_group": date_group,
            "time_label": time_label,
            "pub_timestamp": pub_dt.isoformat(),
            "bullets": bullets,
            "related_articles": [],
            "is_major": is_major,
            "image_url": article_img
        })

    # [과거 기사 보존 및 3개월(90일) 보관 기간 제한 적용]
    seen_processed_links = {a.get("link") for a in processed_articles if a.get("link")}
    seen_processed_titles = {re.sub(r"[^\w가-힣]", "", a.get("title", "")) for a in processed_articles}

    cumulative_articles = list(processed_articles)
    for old_art in existing_articles:
        old_link = old_art.get("link")
        old_clean_t = re.sub(r"[^\w가-힣]", "", old_art.get("title", ""))
        if old_link and old_link in seen_processed_links:
            continue
        if old_clean_t and old_clean_t in seen_processed_titles:
            continue
        
        # 3개월(90일) 지난 기사는 파일 비대화 및 성능 저하 방지를 위해 자동 정리
        if old_art.get("pub_timestamp", "") < cutoff_iso:
            continue

        cumulative_articles.append(old_art)

    # 전체 누적 기사를 최신 발행시각(pub_timestamp) 기준 내림차순 정렬
    cumulative_articles.sort(key=lambda x: x.get("pub_timestamp", ""), reverse=True)
    print(f">> 전체 3개월 누적 보존 기사 건수: {len(cumulative_articles)}건 (이번 신규/수집: {len(processed_articles)}건)")

    # 신규 기사 텔레그램 알림 자동 발송 (새로 수집된 기사만 선별 전송)
    telegram_enabled = bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
    new_sent_count = 0

    for art in processed_articles:
        link = art.get("link")
        if link in existing_sent_links:
            art["telegram_sent"] = True
            continue

        if telegram_enabled:
            print(f">> [텔레그램 신규 기사 발송] {art['title'][:25]}...")
            success = send_telegram_alert(art)
            art["telegram_sent"] = success
            if success:
                new_sent_count += 1
                time.sleep(1)
        else:
            art["telegram_sent"] = False

    if telegram_enabled:
        print(f">> 텔레그램 알림: 총 {new_sent_count}건의 신규 기사 발송 완료")

    # 통계 집계 (전체 누적 기사 기준)
    now_str = now_kst.strftime("%Y.%m.%d. %H:%M")
    major_count = sum(1 for a in cumulative_articles if a.get("is_major", False))
    live_count = len(cumulative_articles) - major_count

    # 1. 언론동향 인기 이슈 키워드 TOP 5 추출 (최근 활성 기사 30건 기준)
    trending_topics = extract_trending_topics(client, cumulative_articles[:30])
    print(f">> 언론동향 키워드 도출 완료: {[t['keyword'] for t in trending_topics]}")

    # 2. 시장·정책관 주간 언론동향 진단 및 7대 테마별 점유율 산출 (최근 7일간 기사 기준)
    recent_week_articles = cumulative_articles[:40]
    macro_pulse = extract_macro_pulse(client, recent_week_articles)
    print(f">> 주간 언론동향 진단 완료 (개요 및 5줄 주요내용, 주의사항 건수: {len(macro_pulse.get('risk_cautions', []))})")

    result_data = {
        "updated_at": now_str,
        "yesterday_label": yesterday_date.strftime("%m.%d"),
        "macro_pulse": macro_pulse,
        "trending_topics": trending_topics,
        "stats": {
            "total": len(cumulative_articles),
            "major_count": major_count,
            "live_count": live_count,
            "today_count": sum(1 for a in cumulative_articles if a.get("date_group") == "TODAY"),
            "yesterday_count": sum(1 for a in cumulative_articles if a.get("date_group") == "YESTERDAY"),
            "policy": sum(1 for a in cumulative_articles if a.get("category") == "POLICY"),
            "culture": sum(1 for a in cumulative_articles if a.get("category") == "CULTURE"),
            "risk": sum(1 for a in cumulative_articles if a.get("category") == "RISK")
        },
        "articles": cumulative_articles
    }

    with open("news_data.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f">> 완료: 총 {len(cumulative_articles)}건 누적 보존 (주요 뉴스 {major_count}건, 실시간 뉴스 {live_count}건) 및 news_data.json 저장 성공")


if __name__ == "__main__":
    main()
