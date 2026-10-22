import email.utils
import html
import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
try:
    from google import genai
except ImportError:
    genai = None
import requests

def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_env_file()

# 1. 환경변수 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")

# 2. 화성시 행정기구 조례 시행규칙 전 부서(82개) 전수 딕셔너리
DEPT_RULES = [
    # [시장 / 부시장 직속 보좌기관]
    {"dept": "공보실 언론담당관", "keywords": ["시정보도", "언론사", "기자회견", "기자브리핑", "기획보도", "시보", "뉴스통신사", "취재지원"]},
    {"dept": "공보실 홍보담당관", "keywords": ["시정홍보", "도시브랜드", "SNS서포터즈", "시정소식지", "홍보대사", "전자전광판", "CF제작", "유튜브"]},
    {"dept": "감사관", "keywords": ["자체감사", "공직기강", "공무원비리", "징계처분", "청렴도", "부패방지", "계약심사", "시민옴부즈만", "고충민원", "공직자재산등록"]},
    {"dept": "트램건설추진단", "keywords": ["도시철도", "트램", "동탄트램", "트램차량기지", "철도안전관리체계", "트램노선", "트램운임"]},
    {"dept": "AI스마트전략실", "keywords": ["인공지능", "스마트도시", "빅데이터", "스마트도시통합운영센터", "지능형선별관제", "데이터플랫폼", "공공데이터", "지정통계"]},
    {"dept": "기본사회담당관", "keywords": ["기본사회", "기본소득", "사회적경제", "협동조합", "마을기업", "공유경제", "공정무역", "사회성과보상"]},

    # [기획조정실]
    {"dept": "기획조정실 정책기획관", "keywords": ["시정종합기획", "주요업무계획", "공약사항", "중장기발전계획", "출자출연기관", "화성시연구원", "공모사업총괄", "시정백서"]},
    {"dept": "기획조정실 균형발전과", "keywords": ["균형발전", "국제테마파크", "서해안발전계획", "테크노폴", "지속가능발전", "경제자유구역", "삼보폐광산", "권역별발전"]},
    {"dept": "기획조정실 의회법무과", "keywords": ["시의회", "행정사무감사", "조례규칙", "자치법규", "행정소송", "행정심판", "고문변호사", "규제개혁", "적극행정", "납세자보호관"]},
    {"dept": "기획조정실 군공항대응과", "keywords": ["군공항", "수원군공항", "화옹지구", "군비행장소음", "군사격장피해", "소음피해보상", "군공항이전"]},
    {"dept": "기획조정실 정보통신과", "keywords": ["정보통신", "행정전산망", "사이버보안", "공공와이파이", "자가통신망", "정보보호", "통합메시징", "정보통신공사감리"]},

    # [안전건설실]
    {"dept": "안전건설실 안전정책과", "keywords": ["재난안전관리", "중대재해", "중대시민재해", "안전지수", "민방위", "을지연습", "시민안전교육", "어린이놀이시설안전"]},
    {"dept": "안전건설실 재난대응과", "keywords": ["자연재난", "사회재난", "재난안전대책본부", "수방자재", "재해구호물자", "자율방재단", "안전한국훈련", "재해위험지구"]},
    {"dept": "안전건설실 건설과", "keywords": ["전문건설업", "골재채취", "국가하천", "소하천정비", "배수펌프장", "농업생산기반", "개간사업", "낚시금지구역"]},
    {"dept": "안전건설실 도로과", "keywords": ["광역도로망", "국도", "지방도", "시도", "도시계획도로", "우회도로", "도로개설", "과적단속", "도로제설", "자전거도로"]},

    # [자치행정국]
    {"dept": "자치행정국 행정지원과", "keywords": ["청사방호", "공무원복무", "공무직노조", "의전", "기록물관리", "행정정보공개", "자매결연", "후생복지"]},
    {"dept": "자치행정국 자치분권과", "keywords": ["자치분권", "지방자치", "특례시", "특례시대도시", "행정구역조정", "고향사랑기부제", "자치경찰제"]},
    {"dept": "자치행정국 시민협력과", "keywords": ["주민자치회", "주민자치센터", "마을공동체", "자원봉사센터", "자율방범대", "민간협력", "사회단체관리"]},
    {"dept": "자치행정국 인사과", "keywords": ["공무원인사", "공무원채용", "인사위원회", "승진심사", "성과상여금", "공무원교육훈련", "시군종합평가"]},
    {"dept": "자치행정국 민원여권과", "keywords": ["여권민원", "가족관계등록", "인감증명", "콜센터", "통합민원발급", "민원상담", "친절행정"]},

    # [재정국]
    {"dept": "재정국 스마트행정종합관찰관", "keywords": ["스마트행정종합관찰제", "생활불편사항", "갈등관리", "국민신문고", "다수인민원", "시민소통광장"]},
    {"dept": "재정국 예산재정과", "keywords": ["지방예산", "추경예산", "재정투자심사", "지방교부세", "지방채", "국도비확보", "주민참여예산", "지방보조금심의"]},
    {"dept": "재정국 세정과", "keywords": ["지방세부과", "취득세", "등록면허세", "개별주택가격", "세무조사", "세외수입", "시금고", "마을세무사"]},
    {"dept": "재정국 징수과", "keywords": ["체납액징수", "체납처분", "부동산압류", "번호판영치", "고액체납자", "결손처분", "징수촉탁"]},
    {"dept": "재정국 회계과", "keywords": ["세출결산", "계약체결", "입찰공고", "조달물품구매", "물품정수", "복식부기", "공사검사", "부정당업자제재"]},
    {"dept": "재정국 재산관리과", "keywords": ["공유재산관리", "시유재산매각", "시청사시설유지", "공용차량관리", "관사관리", "유휴공간개방"]},

    # [돌봄복지국]
    {"dept": "돌봄복지국 복지정책과", "keywords": ["국민기초생활보장", "기초수급자", "사회복지기금", "의료급여", "국가유공자예우", "보훈단체", "노숙인보호", "자활근로"]},
    {"dept": "돌봄복지국 통합돌봄과", "keywords": ["지역사회통합돌봄", "복지사각지대", "고독사예방", "긴급복지지원", "위기가구발굴", "지역사회보장협의체", "기부식품"]},
    {"dept": "돌봄복지국 장애인복지과", "keywords": ["장애인복지", "장애인연금", "장애인일자리", "장애인복지관", "발달장애인", "장애인전용주차구역단속", "장애인편의시설"]},
    {"dept": "돌봄복지국 중장년노인과", "keywords": ["노인복지", "기초연금", "경로당지원", "노인일자리", "장기요양기관", "노인복지관", "노인의료복지시설", "중장년지원"]},
    {"dept": "돌봄복지국 위생정책과", "keywords": ["식품위생", "공중위생", "음식점위생등급제", "식품진흥기금", "식품허위과대광고", "위생감시원", "함백산추모공원", "공설장사시설"]},

    # [성평등가족국]
    {"dept": "성평등가족국 저출생대응과", "keywords": ["인구정책", "저출생대응", "출산지원금", "다자녀정책", "첫만남이용권", "양성평등", "여성친화도시", "한부모가족", "가족센터"]},
    {"dept": "성평등가족국 영유아보육과", "keywords": ["어린이집", "시립어린이집", "국공립어린이집", "보육료지원", "양육수당", "부모급여", "육아종합지원센터", "아이키움터"]},
    {"dept": "성평등가족국 아동친화과", "keywords": ["아동친화도시", "아동학대조사", "드림스타트", "지역아동센터", "다함께돌봄센터", "어린이날기념행사", "결식아동"]},
    {"dept": "성평등가족국 청년청소년과", "keywords": ["청년정책", "청년일자리", "청년지원센터", "청소년수련관", "학교밖청소년", "고립은둔청년", "청소년유해환경"]},
    {"dept": "성평등가족국 이주민지원과", "keywords": ["이주민지원", "다문화가족", "외국인주민", "외국인근로자", "다문화도시", "외국인복지센터", "글로벌청소년센터"]},

    # [농정해양국]
    {"dept": "농정해양국 농업정책과", "keywords": ["공익직불제", "농지관리", "농지진흥지역", "농지법", "벼병해충방제", "후계농업인", "친환경농업", "농업재해", "농어업경영자금"]},
    {"dept": "농정해양국 농식품유통과", "keywords": ["로컬푸드", "화성푸드플랜", "공공급식지원센터", "학교무상급식", "햇살드리", "수향미", "송산포도축제", "직매장"]},
    {"dept": "농정해양국 축산정책과", "keywords": ["축산정책", "가축방역", "아프리카돼지열병", "조류인플루엔자", "구제역", "가축분뇨처리", "축산악취저감", "축사현대화"]},
    {"dept": "농정해양국 동물보호과", "keywords": ["반려동물", "유기동물구조", "반려견놀이터", "동물보호센터", "길고양이중성화", "맹견관리", "반려동물병원"]},
    {"dept": "농정해양국 해양수산과", "keywords": ["전곡항", "궁평항", "어항개발", "어선등록", "양식어업", "수산자원조성", "해양쓰레기", "불법어업단속", "연안체험활동"]},

    # [교통국]
    {"dept": "교통국 교통정책과", "keywords": ["도시교통정비", "교통안전기본계획", "지능형교통체계", "ITS", "버스정보시스템", "BIS", "교통약자이동지원", "개인형이동장치", "PM"]},
    {"dept": "교통국 철도전략과", "keywords": ["광역철도망", "GTX", "신안산선", "동탄인덕원선", "서해선복선전철", "복합환승센터", "철도유치", "철도역사"]},
    {"dept": "교통국 대중교통과", "keywords": ["시내버스", "마을버스", "광역버스", "버스공영제", "공영버스", "택시요금", "버스전용차로", "유가보조금", "수요응답형버스"]},
    {"dept": "교통국 주차물류과", "keywords": ["공영주차장", "거주자우선주차", "주차타워", "불법주정차단속", "주차단속CCTV", "화물차공영차고지", "물류단지개발"]},
    {"dept": "교통국 차량등록과", "keywords": ["자동차등록", "번호판교부", "건설기계등록", "자동차과태료", "자동차의무보험", "무단방치자동차", "불법튜닝단속"]},

    # [도시정책실]
    {"dept": "도시정책실 도시정책과", "keywords": ["2040도시기본계획", "도시관리계획", "지구단위계획", "개발밀도관리", "기반시설부담구역", "성장관리계획", "개발제한구역"]},
    {"dept": "도시정책실 도시계획상임기획단", "keywords": ["도시계획위원회", "도시경관", "경관계획", "도시디자인", "공공디자인", "유니버설디자인", "설계공모"]},
    {"dept": "도시정책실 도시개발과", "keywords": ["도시개발사업", "환지계획", "송산그린시티", "도시재생사업", "빈집정비", "개발행위허가", "농지전용허가", "산지전용허가"]},
    {"dept": "도시정책실 신도시조성과", "keywords": ["동탄신도시", "공공주택지구", "택지개발지구", "신도시기반시설", "시범도시개발"]},
    {"dept": "도시정책실 토지정보과", "keywords": ["개별공시지가", "지적재조사", "부동산실거래가", "지적측량", "도로명주소", "공간정보체계", "개발부담금"]},

    # [기업투자실]
    {"dept": "기업투자실 첨단산업과", "keywords": ["반도체클러스터", "미래모빌리티", "자율주행리빙랩", "도심항공교통", "UAM", "드론경진대회", "바이오산업", "특화단지"]},
    {"dept": "기업투자실 기업지원과", "keywords": ["중소기업지원", "기업애로사항", "소공인지원", "중소기업육성자금", "수출지원", "공장설립승인", "화성산업진흥원"]},
    {"dept": "기업투자실 투자유치과", "keywords": ["기업투자유치", "대규모투자MOU", "외국계기업유치", "산업단지개발", "준산업단지", "지식산업센터기업유치"]},
    {"dept": "기업투자실 지역경제과", "keywords": ["지역화폐", "희망화성지역화폐", "소상공인지원", "전통시장활성화", "상점가육성", "물가안정", "소상공인특례보증"]},
    {"dept": "기업투자실 노사협력과", "keywords": ["지방노동정책", "근로자종합복지관", "노사민정", "산업재해예방", "일자리창출", "화성시일자리센터", "취업박람회", "생활임금"]},

    # [문화관광국]
    {"dept": "문화관광국 문화예술과", "keywords": ["화성시문화재단", "화성예술의전당", "시립미술관", "동탄복합문화센터", "문화예술축제", "노작홍사용문학관", "문화도시"]},
    {"dept": "문화관광국 문화유산과", "keywords": ["국가유산", "향토유산", "지정문화유산", "전통사찰보수", "역사박물관", "유물조사", "당성발굴", "화성시사편찬"]},
    {"dept": "문화관광국 독립기념관", "keywords": ["화성시독립운동기념관", "3.1운동", "독립운동자료", "독립기념사업", "미서훈독립운동가"]},
    {"dept": "문화관광국 관광진흥과", "keywords": ["화성뱃놀이축제", "서해안관광단지", "제부도케이블카", "국가지질공원", "시티투어", "해양레저스포츠", "매향리평화기념관"]},

    # [교육체육국]
    {"dept": "교육체육국 교육지원과", "keywords": ["교육발전특구", "학교교육경비지원", "화성시인재육성재단", "학교복합시설", "특화고설립", "화성시장학관"]},
    {"dept": "교육체육국 평생학습과", "keywords": ["평생학습관", "화성시민대학", "평생교육프로그램", "평생학습동아리", "학습소외계층지원"]},
    {"dept": "교육체육국 도서관정책과", "keywords": ["시립도서관", "중앙도서관", "공공도서관", "작은도서관", "독서문화진흥", "도서관상호대차"]},
    {"dept": "교육체육국 체육진흥과", "keywords": ["생활체육", "공공체육시설", "화성종합경기타운", "시민체육대회", "장애인체육", "직장운동경기부", "화성드림파크"]},
    {"dept": "교육체육국 전국체전추진단", "keywords": ["전국체육대회", "전국체전", "장애인체전", "체전종합계획", "체전경기장신축개보수"]},

    # [주택국]
    {"dept": "주택국 주택정책과", "keywords": ["기본주택정책", "주택건설사업계획승인", "재건축정비사업", "분양가심사", "주거급여", "주거복지센터", "리모델링지원"]},
    {"dept": "주택국 공동주택과", "keywords": ["공동주택관리", "아파트입주자대표회의", "관리비감사", "임대주택분양전환", "아파트품질점검", "공동주택안전관리"]},
    {"dept": "주택국 건축과", "keywords": ["건축허가", "건축신고", "위반건축물단속", "불법건축물", "지역건축안전센터", "옥외광고물허가", "불법현수막정비"]},
    {"dept": "주택국 공공건축과", "keywords": ["공공청사건립", "복합복지시설신축", "공공건축물설계", "시공감독", "청사증축개축"]},

    # [기후에너지환경국]
    {"dept": "기후에너지환경국 기후환경정책과", "keywords": ["탄소중립포인트", "온실가스배출권", "노후경유차매연저감", "미세먼지계절관리제", "친환경차보급", "수소전기차", "화성시환경재단"]},
    {"dept": "기후에너지환경국 신재생에너지과", "keywords": ["신재생에너지", "RE100", "태양광발전", "풍력발전", "수소연료전지", "에너지자립마을", "도시가스배관망", "전기안전관리"]},
    {"dept": "기후에너지환경국 물환경생태과", "keywords": ["수질오염총량관리", "시화호수질개선", "비봉습지공원", "야생동물구조", "물순환시스템", "공공폐수처리시설", "비점오염저감"]},
    {"dept": "기후에너지환경국 자원순환과", "keywords": ["생활폐기물처리", "쓰레기종량제봉투", "음식물쓰레기감량", "그린환경센터", "폐기물소각장", "재활용선별장", "불법폐기물투기"]},
    {"dept": "기후에너지환경국 환경지도과", "keywords": ["환경오염사고방제", "오염배출업소단속", "폐수무단방류", "대기배출시설점검", "환경신문고", "공사장소음진동", "사업장폐기물단속"]},

    # [직속기관 & 사업소]
    {"dept": "화성시보건소 보건정책과", "keywords": ["지역보건의료계획", "감염병총괄대응", "코로나19", "역학조사", "감염병방역대책", "응급의료체계", "의약품지도"]},
    {"dept": "화성시보건소 건강증진과", "keywords": ["시민건강증진", "금연클리닉", "모자보건지원", "국가암검진", "치매안심센터", "만성질환예방", "방문건강관리"]},
    {"dept": "농업기술센터 기술기획과", "keywords": ["농촌지도사업", "귀농귀촌지원센터", "강소농육성", "농업인대학", "도시농업체험", "농산물가공창업"]},
    {"dept": "농업기술센터 기술보급과", "keywords": ["식량작물재배지도", "스마트팜권역별지원", "농작물돌발병해충", "과수재배시범사업", "정부보급종자"]},
    {"dept": "농업기술센터 과학농업과", "keywords": ["농산물안전성분석", "비료사용처방서", "유용미생물배양실", "PLS농약허용목록", "농업기계임대사업소"]},
    {"dept": "맑은물사업소 맑은물운영과", "keywords": ["상수도공기업회계", "상수도요금부과", "상수원보호구역", "먹는물수질검사", "지하수개발관리"]},
    {"dept": "맑은물사업소 맑은물시설과", "keywords": ["수도정비기본계획", "수돗물수질평가", "송배수관망유지관리", "노후수도관교체", "스마트상수도구축", "유수율제고"]},
    {"dept": "맑은물사업소 하수과", "keywords": ["하수도정비기본계획", "공공하수처리장", "하수관로BTL", "하수도사용료", "하수슬러지처리", "분뇨처리시설"]},
    {"dept": "공원녹지사업소 공원조성과", "keywords": ["공원녹지기본계획", "도시공원조성", "쌈지공원조경", "우리꽃식물원운영", "마을정원만들기"]},
    {"dept": "공원녹지사업소 서부공원관리과", "keywords": ["서부권도시공원유지관리", "어린이공원정비", "공원물놀이시설관리", "공원내불법행위단속"]},
    {"dept": "공원녹지사업소 동부공원관리과", "keywords": ["동부권도시공원유지관리", "동탄호수공원루나분수", "동탄센트럴파크관리", "동부공원시설정비"]},
    {"dept": "공원녹지사업소 산림휴양과", "keywords": ["산불방지대책본부", "산림병해충방제", "소나무재선충", "도시가로수식재", "숲길등산로정비", "사방사업"]},
    {"dept": "공원녹지사업소 보타닉가든추진단", "keywords": ["보타닉가든", "보타닉가든화성", "도심수목원조성", "사계절온실식물원", "보타닉가든브랜딩"]},
    {"dept": "대외협력사무소", "keywords": ["국회대외협력", "정부예산확보지원", "중앙부처협력", "세종시대외사무소"]}
]

BUREAU_LIST = [
    "공보실", "기획조정실", "안전건설실", "자치행정국", "재정국", "돌봄복지국",
    "성평등가족국", "농정해양국", "교통국", "도시정책실", "기업투자실", "문화관광국",
    "교육체육국", "주택국", "기후에너지환경국", "맑은물사업소", "공원녹지사업소",
    "농업기술센터", "화성시보건소", "보건소", "대외협력사무소"
]

RISK_KEYWORDS = [
    "논란", "의혹", "비리", "징계", "압수수색", "감사", "적발", "수사", "횡령",
    "과태료", "고발", "조사", "갈등", "반발", "침수", "악취", "피해", "단속", "과징금"
]
CULTURE_KEYWORDS = [
    "축제", "공연", "전시", "체험", "행사", "문화", "페스티벌", "개최", "음악회", "대회", "기념식"
]


def clean_html(text):
    if not text:
        return ""
    unescaped = html.unescape(text)
    return re.sub(r"<[^>]+>", "", unescaped).strip()


def extract_media_name(link, originallink, default_media=""):
    if default_media and default_media not in ("언론사", ""):
        return default_media
    target = (originallink or link or "").lower()
    media_map = {
        "yna.co.kr": "연합뉴스",
        "kyeongin.com": "경인일보",
        "kgnews.co.kr": "경기일보",
        "joongboo.com": "중부일보",
        "newsis.com": "뉴시스",
        "news1.kr": "뉴스1",
        "kihoilbo.co.kr": "기호일보",
        "ytn.co.kr": "YTN",
        "kbs.co.kr": "KBS",
        "mbc.co.kr": "MBC",
        "sbs.co.kr": "SBS",
        "chosun.com": "조선일보",
        "donga.com": "동아일보",
        "joins.com": "중앙일보",
        "hani.co.kr": "한겨레",
        "khan.co.kr": "경향신문",
        "hankyung.com": "한국경제",
        "mk.co.kr": "매일경제",
        "fnnews.com": "파이낸셜뉴스",
        "sedaily.com": "서울경제",
        "nocutnews.co.kr": "노컷뉴스",
    }
    for domain, name in media_map.items():
        if domain in target:
            return name
    return default_media or "언론사"


def parse_pub_date(date_str):
    """RFC 2822 형식의 날짜 문자열을 KST datetime으로 변환"""
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        kst = timezone(timedelta(hours=9))
        return dt.astimezone(kst)
    except Exception:
        return datetime.now(timezone(timedelta(hours=9)))


def fetch_news():
    enc_query = urllib.parse.quote("화성시")
    headers_common = {"User-Agent": "Mozilla/5.0"}

    # 1. 네이버 API 키가 있는 경우 우선 시도
    if NAVER_CLIENT_ID and NAVER_CLIENT_SECRET:
        cid = NAVER_CLIENT_ID.strip()
        csec = NAVER_CLIENT_SECRET.strip()

        # 1-1. 네이버 개발자센터 오픈 API (developers.naver.com)
        url_dev = f"https://openapi.naver.com/v1/search/news.json?query={enc_query}&display=100&start=1&sort=date"
        headers_dev = {
            "X-Naver-Client-Id": cid,
            "X-Naver-Client-Secret": csec,
            **headers_common
        }
        try:
            res = requests.get(url_dev, headers=headers_dev, timeout=10)
            if res.ok:
                items = res.json().get("items", [])
                if items:
                    print(f">> 네이버 오픈 API(developers.naver.com)에서 {len(items)}건 수집 완료")
                    return items
        except Exception as e:
            print(f"네이버 오픈 API 통신 에러: {e}")

        # 1-2. 네이버 클라우드 플랫폼 (ncloud / apigw.ntruss.com)
        url_ncp = f"https://naverapihub.apigw.ntruss.com/search/v1/news?query={enc_query}&display=100&start=1&sort=date&format=json"
        headers_ncp = {
            "X-NCP-APIGW-API-KEY-ID": cid,
            "X-NCP-APIGW-API-KEY": csec,
            **headers_common
        }
        try:
            res = requests.get(url_ncp, headers=headers_ncp, timeout=10)
            if res.ok:
                items = res.json().get("items", [])
                if items:
                    print(f">> 네이버 클라우드 API(apigw.ntruss.com)에서 {len(items)}건 수집 완료")
                    return items
        except Exception as e:
            print(f"네이버 클라우드 API 통신 에러: {e}")

    # 2. API 키 미설정 또는 실패 시 공개 뉴스 RSS 피드 자동 대체 수집
    print(">> 실시간 공개 뉴스 피드(화성시)로 뉴스 수집을 진행합니다...")
    try:
        rss_url = f"https://news.google.com/rss/search?q={enc_query}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(rss_url, headers=headers_common, timeout=10)
        if res.ok:
            root = ET.fromstring(res.content)
            rss_items = root.findall(".//item")
            parsed_items = []
            for it in rss_items:
                title_raw = it.findtext("title", "")
                link = it.findtext("link", "")
                pub_date = it.findtext("pubDate", "")
                desc = it.findtext("description", "")
                source_el = it.find("source")
                source_name = source_el.text if source_el is not None else ""

                clean_t = title_raw
                if " - " in title_raw:
                    parts = title_raw.rsplit(" - ", 1)
                    clean_t = parts[0]
                    if not source_name:
                        source_name = parts[1]

                parsed_items.append({
                    "title": clean_t,
                    "description": desc or clean_t,
                    "link": link,
                    "originallink": link,
                    "pubDate": pub_date,
                    "media": source_name
                })
            print(f">> 실시간 뉴스 피드에서 {len(parsed_items)}건 수집 완료")
            return parsed_items
    except Exception as e:
        print(f"실시간 뉴스 피드 수집 실패: {e}")

    return []


def classify_category(title, desc):
    full_text = f"{title} {desc}"
    clean_full = full_text.replace(" ", "")
    for kw in RISK_KEYWORDS:
        if kw in full_text or kw.replace(" ", "") in clean_full:
            return "RISK"
    for kw in CULTURE_KEYWORDS:
        if kw in full_text or kw.replace(" ", "") in clean_full:
            return "CULTURE"
    return "POLICY"


def match_department(title, desc):
    full_text = f"{title} {desc}"
    clean_full = full_text.replace(" ", "")
    clean_title = title.replace(" ", "")
    clean_desc = desc.replace(" ", "")

    # 1단계: 정식 부서명 직접 일치
    for rule in DEPT_RULES:
        dept_name = rule["dept"].split()[-1]
        if dept_name in full_text or dept_name in clean_full:
            return rule["dept"]

    # 2단계: 조례 분장사무 키워드 채점
    best_dept = None
    max_score = 0
    for rule in DEPT_RULES:
        score = 0
        for kw in rule["keywords"]:
            clean_kw = kw.replace(" ", "")
            if kw in title or clean_kw in clean_title:
                score += 3
            elif kw in desc or clean_kw in clean_desc:
                score += 1
        if score > max_score:
            max_score = score
            best_dept = rule["dept"]

    if max_score > 0:
        return best_dept

    # 3단계: 국/실/사업소 단위 표기
    for bureau in BUREAU_LIST:
        if bureau in full_text or bureau.replace(" ", "") in clean_full:
            return bureau

    return "화성시 소관부서 확인중"


def generate_bullets(title, desc):
    clean_desc = desc.strip()
    if not clean_desc or len(clean_desc) < 15:
        return ["본문 정보 부족으로 세부 요약을 생략합니다."]

    if GEMINI_API_KEY and genai:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY.strip())
            prompt = (
                f"기사 제목: {title}\n"
                f"기사 내용: {clean_desc}\n\n"
                "[지침]\n"
                "1. 제공된 내용만을 바탕으로 핵심 사실을 간결한 한국어 3줄 요약 불릿으로 작성하십시오.\n"
                "2. 각 줄은 반드시 '- ' 기호로 시작하십시오.\n"
                "3. 사족이나 서두 없이 3개의 불릿 라인만 출력하십시오."
            )
            for model_name in [os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"), "gemini-1.5-flash"]:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )
                    if response and response.text:
                        lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
                        return lines[:3]
                except Exception:
                    continue
        except Exception as e:
            print(f"Gemini 요약 예외: {e}")

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_desc) if len(s.strip()) > 8]
    if len(sentences) >= 2:
        return [f"- {s}" for s in sentences[:3]]
    return [f"- {clean_desc}"]


def cluster_and_filter_articles(raw_items):
    """최근 48시간(오늘+어제) 기사 필터링 및 유사 기사 클러스터링"""
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    today_date = now_kst.date()
    yesterday_date = today_date - timedelta(days=1)

    clusters = []

    for item in raw_items:
        pub_dt = parse_pub_date(item.get("pubDate", ""))
        item_date = pub_dt.date()

        # 오늘과 어제가 아닌 기사(2일 이전)는 제외
        if item_date not in (today_date, yesterday_date):
            continue

        title = clean_html(item.get("title", ""))
        desc = clean_html(item.get("description", ""))
        link = item.get("originallink", "") or item.get("link", "")
        media = extract_media_name(item.get("link", ""), item.get("originallink", ""), default_media=item.get("media", ""))

        if not title:
            continue

        tokens = set(re.findall(r"[가-힣]{2,}", title))
        tokens.discard("화성시")
        tokens.discard("화성")

        matched_cluster = None
        for c in clusters:
            common = tokens.intersection(c["tokens"])
            if len(common) >= 2:
                matched_cluster = c
                break

        if matched_cluster:
            # 더 최신 기사면 대표 기사 메타 업데이트
            if pub_dt > matched_cluster["pub_dt"]:
                matched_cluster["related"].append({
                    "media": matched_cluster["media"],
                    "title": matched_cluster["title"],
                    "link": matched_cluster["link"]
                })
                matched_cluster["title"] = title
                matched_cluster["desc"] = desc
                matched_cluster["link"] = link
                matched_cluster["media"] = media
                matched_cluster["pub_dt"] = pub_dt
            else:
                matched_cluster["related"].append({
                    "media": media,
                    "title": title,
                    "link": link
                })
        else:
            clusters.append({
                "title": title,
                "desc": desc,
                "link": link,
                "media": media,
                "pub_dt": pub_dt,
                "tokens": tokens,
                "related": []
            })

    # 최신 기사가 맨 위로 오도록 내림차순 정렬
    clusters.sort(key=lambda x: x["pub_dt"], reverse=True)
    return clusters, today_date, yesterday_date


def main():
    print("화성시 최근 48시간(오늘+어제) 뉴스 수집 및 분석 시작...")
    raw_items = fetch_news()
    if not raw_items:
        print("수집된 뉴스가 없습니다.")
        return

    clusters, today_date, yesterday_date = cluster_and_filter_articles(raw_items)
    print(f"최근 48시간 유효 기사 클러스터: {len(clusters)}건 형성 (최신순 정렬 완료)")

    kst = timezone(timedelta(hours=9))
    now_str = datetime.now(kst).strftime("%Y.%m.%d. %H:%M")

    processed_articles = []
    today_cnt = 0
    yesterday_cnt = 0
    policy_cnt = 0
    culture_cnt = 0
    risk_cnt = 0

    # 최대 35개 주요 이슈 처리
    for c in clusters[:35]:
        cat = classify_category(c["title"], c["desc"])
        dept = match_department(c["title"], c["desc"])
        bullets = generate_bullets(c["title"], c["desc"])

        is_today = (c["pub_dt"].date() == today_date)
        if is_today:
            today_cnt += 1
            date_group = "TODAY"
            time_label = f"오늘 {c['pub_dt'].strftime('%H:%M')}"
        else:
            yesterday_cnt += 1
            date_group = "YESTERDAY"
            time_label = f"어제 {c['pub_dt'].strftime('%H:%M')}"

        if cat == "POLICY": policy_cnt += 1
        elif cat == "CULTURE": culture_cnt += 1
        elif cat == "RISK": risk_cnt += 1

        processed_articles.append({
            "title": c["title"],
            "link": c["link"],
            "media": c["media"],
            "category": cat,
            "department": dept,
            "date_group": date_group,
            "time_label": time_label,
            "pub_timestamp": c["pub_dt"].isoformat(),
            "bullets": bullets,
            "related_articles": c["related"][:5]
        })
        if GEMINI_API_KEY:
            time.sleep(0.5)

    result_data = {
        "updated_at": now_str,
        "yesterday_label": yesterday_date.strftime("%m.%d"),
        "stats": {
            "total": len(processed_articles),
            "today_count": today_cnt,
            "yesterday_count": yesterday_cnt,
            "policy": policy_cnt,
            "culture": culture_cnt,
            "risk": risk_cnt
        },
        "articles": processed_articles
    }

    with open("news_data.json", "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)

    print(f">> news_data.json 저장 완료 (오늘: {today_cnt}건, 어제: {yesterday_cnt}건)")


if __name__ == "__main__":
    main()