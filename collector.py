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
    """Gemini 3.8 Flash를 활용한 시정 관련성 판별, 3줄 요약 및 리스크 대응방향 도출"""
    prompt = f"""당신은 화성시청 언론홍보 및 리스크 분석 수석 실무관입니다.
아래 기사를 정밀 분석하여 화성시 행정/시정과 관련된 기사인지 엄격히 검증하고 JSON으로 출력하십시오.

[기사 제목]: {title}
[기사 내용]:
{content}
[1차 추천 소관부서]: {rule_dept}

[작업 지침 - 매우 엄격한 화성시정 핵심 관련성 검증]
1. is_hwaseong_news (반드시 true 또는 false):
   - [반드시 true로 판별할 조건]:
     * 기사의 '주된 보도 대상(핵심 주제)'이 화성시(시청, 시장, 시의회, 산하기관, 관내 사업소 등)의 고유 정책, 자체 추진 사업, 직접 주최 행사, 관내 주요 현안 및 중대 사건사고인 경우.
     * 기사 분량의 대부분이 화성시의 행정과 시민에 초점을 맞추고 있는 경우.

   - [반드시 false로 엄격 제외할 조건 - 예외 없음]:
     * 본문에 '화성'이나 '화성시'가 1~2회 단순 참석, 내빈 나열, 타 지자체 경유 등으로 스쳐 지나간 기사 (예: 타 지자체 의회나 협의회 행사에 화성시 관계자가 단순 참석한 기사).
     * 거시경제, 전국 증시, 환율, 금리, 전국 부동산 아파트 분양/시세 통계 기사에서 '화성 사업장', '화성시 반송동' 등이 단순 수치나 지명 예시로 1줄 언급된 경우.
     * 전국 지자체 목록 중 하나로 화성시가 곁가지로 나열된 기사.
     * 기사의 주어와 주된 내용이 화성시정이 아닌 기사.

2. category (is_hwaseong_news가 true일 때만 유효):
   - RISK: 시정 비판, 비리/의혹, 수사/감사 적발, 집단 민원 갈등, 대형 안전/환경 사고.
   - CULTURE: 행사, 축제, 대회, 전시, 포럼, 포상 수상.
   - POLICY: 일반 시정 홍보, 지원 사업, 협약(MOU), 도시 인프라 개발.

3. department: 기사 내용에 가장 부합하는 화성시 소관 실·과명 (기사와 무관하면 "해당없음").

4. bullets: 화성시 행정과 관련된 구체적 사실 중심의 3줄 핵심 요약 (각 줄은 '- '로 시작).

5. response_direction:
   - 기사가 'RISK'(비판/지적/의혹/갈등/사고)인 경우:
     지자체 담당 공무원이 취해야 할 실무 대응방향을 신속한 현장 조치 및 공보 대응 관점에서 명확하고 객관적인 1줄 요약으로 제시하십시오.
     (예: "관내 현장 사실관계 즉시 확인 및 왜곡 보도 여부 검토 후 공보실과 정정·해명자료 배포 검토", "소관 부서 긴급 대책회의 소집 및 재발 방지 종합 대책 수립")
   - RISK가 아닌 일반 정책(POLICY)이나 문화행사(CULTURE)인 경우 반드시 빈 문자열 ""을 반환하십시오.

[출력 JSON 형식]:
{{
  "is_hwaseong_news": true | false,
  "category": "POLICY" | "CULTURE" | "RISK",
  "department": "소관부서명",
  "bullets": [
    "- 첫 번째 핵심 요약",
    "- 두 번째 핵심 요약",
    "- 세 번째 핵심 요약"
  ],
  "response_direction": "실무 대응방향 1줄 요약 (RISK일 때만 작성, 그 외에는 빈 문자열)"
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
            resp_dir = data.get("response_direction", "").strip() if data.get("category") == "RISK" else ""
            return (
                is_valid,
                data.get("category", "POLICY"),
                data.get("department", rule_dept),
                data.get("bullets", [])[:3],
                resp_dir
            )
    except Exception as e:
        print(f"Gemini 호출 에러 ({title[:20]}): {e}")

    # Fallback: 제목에 '화성'이 명시되어 있지 않으면 무관한 기사로 탈락
    is_fallback_valid = ("화성" in title)
    return is_fallback_valid, "POLICY", rule_dept, [
        f"- {title}",
        f"- {content[:120]}...",
        "- 상세 내용은 기사 원문을 확인하시기 바랍니다."
    ], ""


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

    # 지적성(RISK) 기사 대응방향 요약 안내
    resp_dir = article.get("response_direction")
    resp_text = f"\n\n💡 <b>실무 대응방향:</b> {html.escape(resp_dir)}" if (resp_dir and article.get("category") == "RISK") else ""

    # 다수 언론사 보도 묶음 안내
    related = article.get("related_articles", [])
    cluster_text = f"\n다수 언론사 보도: 총 {len(related) + 1}개사 집중 보도" if related else ""

    caption = (
        f"<b>[{sec_title} | {cat_name}]</b>\n"
        f"<a href=\"{article['link']}\"><b>{html.escape(article['title'])}</b></a>\n\n"
        f"{clean_bullets}{resp_text}\n\n"
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

    # 기존 news_data.json의 기사 목록 로드 (중복 텔레그램 발송 방지 및 Gemini API 캐시 재활용)
    existing_sent_links = set()
    existing_articles_map = {}
    existing_title_map = {}
    if os.path.exists("news_data.json"):
        try:
            with open("news_data.json", "r", encoding="utf-8") as f:
                old_data = json.load(f)
                for old_art in old_data.get("articles", []):
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

    for item in raw_items:
        pub_dt = parse_pub_date(item.get("pubDate", ""))
        item_date = pub_dt.date()

        if item_date not in (today_date, yesterday_date):
            continue

        title = clean_html(item.get("title", ""))
        desc = clean_html(item.get("description", ""))
        link = item.get("originallink", "") or item.get("link", "")
        media = extract_media_name(item.get("link", ""), item.get("originallink", ""))

        is_today = (item_date == today_date)
        time_label = f"오늘 {pub_dt.strftime('%H:%M')}" if is_today else f"어제 {pub_dt.strftime('%H:%M')}"
        date_group = "TODAY" if is_today else "YESTERDAY"

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
            processed_articles.append({
                "title": title,
                "link": link,
                "media": media,
                "category": cached.get("category", "POLICY"),
                "department": cached.get("department", "공보실"),
                "dept_label": cached.get("dept_label", "참고"),
                "date_group": date_group,
                "time_label": time_label,
                "pub_timestamp": pub_dt.isoformat(),
                "bullets": cached.get("bullets", []),
                "related_articles": cached.get("related_articles", []),
                "is_major": cached.get("is_major", False),
                "image_url": cached.get("image_url", ""),
                "response_direction": cached.get("response_direction", ""),
                "telegram_sent": True
            })
            print(f"   -> [API 캐시 재활용 (비용 0원)] {title[:20]}...")
            if len(processed_articles) >= 25:
                break
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

        # 4. Gemini 실무 요약 및 판별
        print(f"분석 중: {title[:25]}...")
        is_valid, cat, dept, bullets, resp_dir = analyze_with_gemini(client, title, article_content, rule_dept)

        # 화성시정과 무관한 전국 경제/단순 지명 언급 기사는 자동 제외
        if not is_valid:
            print(f"   -> [제외] 화성시정 무관 기사 필터링: {title[:20]}")
            continue

        # 소관 vs 참고 부서 판별 (기사 본문에 해당 부서가 직접 언급되어 있으면 '소관', 아니면 '참고')
        dept_short_name = dept.split()[-1] if dept else ""
        is_mentioned = bool(dept_short_name and (dept_short_name in article_content or (dept and dept in article_content)))
        dept_label = "소관" if is_mentioned else "참고"

        # 주요 뉴스 판별 (비판/리스크 기사는 기본 주요 뉴스로 등록)
        is_major = (cat == "RISK")

        processed_articles.append({
            "title": title,
            "link": link,
            "media": media,
            "category": cat,
            "department": dept,
            "dept_label": dept_label,
            "date_group": date_group,
            "time_label": time_label,
            "pub_timestamp": pub_dt.isoformat(),
            "bullets": bullets,
            "related_articles": [],
            "is_major": is_major,
            "image_url": article_img,
            "response_direction": resp_dir
        })

        if len(processed_articles) >= 25:
            break

    # 신규 기사 텔레그램 알림 자동 발송 (새로 수집된 기사만 선별 전송)
    telegram_enabled = bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
    new_sent_count = 0

    for art in processed_articles:
        link = art.get("link")
        # 이미 이전 실행에서 수집/전송된 기사는 건너뜀
        if link in existing_sent_links:
            art["telegram_sent"] = True
            continue

        if telegram_enabled:
            print(f">> [텔레그램 신규 기사 발송] {art['title'][:25]}...")
            success = send_telegram_alert(art)
            art["telegram_sent"] = success
            if success:
                new_sent_count += 1
                time.sleep(1)  # 텔레그램 API 호출 제한 준수
        else:
            art["telegram_sent"] = False

    if telegram_enabled:
        print(f">> 텔레그램 알림: 총 {new_sent_count}건의 신규 기사 발송 완료")

    # 통계 집계
    now_str = now_kst.strftime("%Y.%m.%d. %H:%M")
    major_count = sum(1 for a in processed_articles if a.get("is_major", False))
    live_count = len(processed_articles) - major_count

    # 실시간 언론동향 인기 이슈 키워드 TOP 5 추출
    trending_topics = extract_trending_topics(client, processed_articles)
    print(f">> 언론동향 키워드 도출 완료: {[t['keyword'] for t in trending_topics]}")

    result_data = {
        "updated_at": now_str,
        "yesterday_label": yesterday_date.strftime("%m.%d"),
        "trending_topics": trending_topics,
        "stats": {
            "total": len(processed_articles),
            "major_count": major_count,
            "live_count": live_count,
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

    print(f">> 완료: 총 {len(processed_articles)}건 분석 (주요 뉴스 {major_count}건, 실시간 뉴스 {live_count}건, 언론동향 {len(trending_topics)}건) 및 news_data.json 저장 성공")


if __name__ == "__main__":
    main()
