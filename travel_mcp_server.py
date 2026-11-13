"""
Travel Info MCP Server (FastMCP, single file)

도구
- get_exchange_rate        : 환율 조회 (통화코드 / 국가명 / 도시명 모두 입력 가능)
- get_weather              : 도시·국가의 현재 날씨 + 일별 예보
- analyze_travel_condition : 환율 + 날씨를 합쳐 여행 환경 분석

데이터 출처
- 환율 : https://open.er-api.com/v6/latest/{BASE}
- 좌표 : https://geocoding-api.open-meteo.com/v1/search
- 날씨 : https://api.open-meteo.com/v1/forecast

실행
    pip install fastmcp httpx truststore   # truststore는 사내망 SSL 문제 시 필요
    python travel_mcp_server.py                 # stdio (Claude Desktop/Code 등)
    python travel_mcp_server.py --http 8000     # Streamable HTTP
"""

from __future__ import annotations

import sys
from typing import Any

import httpx
from fastmcp import FastMCP

# 사내망(TLS 검사 프록시) 환경에서도 동작하도록 OS 인증서 저장소를 사용 (설치된 경우)
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

EXCHANGE_URL = "https://open.er-api.com/v6/latest/{base}"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT = 15.0

mcp = FastMCP(
    name="travel-info",
    instructions=(
        "환율, 날씨, 여행 환경 분석 도구를 제공합니다. "
        "통화는 ISO 코드(USD, JPY) 또는 국가/도시 이름(일본, Tokyo)으로 지정할 수 있습니다."
    ),
)

# --------------------------------------------------------------------------
# 참조 데이터
# --------------------------------------------------------------------------

# ISO 3166-1 alpha-2 국가코드 -> 통화코드
COUNTRY_TO_CURRENCY: dict[str, str] = {
    "KR": "KRW", "US": "USD", "JP": "JPY", "CN": "CNY", "HK": "HKD", "TW": "TWD",
    "MO": "MOP", "SG": "SGD", "TH": "THB", "VN": "VND", "PH": "PHP", "MY": "MYR",
    "ID": "IDR", "IN": "INR", "KH": "KHR", "LA": "LAK", "MN": "MNT", "NP": "NPR",
    "LK": "LKR", "MV": "MVR", "AU": "AUD", "NZ": "NZD", "CA": "CAD", "MX": "MXN",
    "BR": "BRL", "AR": "ARS", "CL": "CLP", "PE": "PEN", "CO": "COP", "GB": "GBP",
    "CH": "CHF", "NO": "NOK", "SE": "SEK", "DK": "DKK", "IS": "ISK", "PL": "PLN",
    "CZ": "CZK", "HU": "HUF", "RO": "RON", "TR": "TRY", "RU": "RUB", "UA": "UAH",
    "AE": "AED", "SA": "SAR", "QA": "QAR", "IL": "ILS", "EG": "EGP", "MA": "MAD",
    "ZA": "ZAR", "KE": "KES", "GU": "USD", "MP": "USD", "PR": "USD",
    # 유로존
    "DE": "EUR", "FR": "EUR", "IT": "EUR", "ES": "EUR", "PT": "EUR", "NL": "EUR",
    "BE": "EUR", "AT": "EUR", "IE": "EUR", "FI": "EUR", "GR": "EUR", "LU": "EUR",
    "SK": "EUR", "SI": "EUR", "EE": "EUR", "LV": "EUR", "LT": "EUR", "MT": "EUR",
    "CY": "EUR", "HR": "EUR", "MC": "EUR", "VA": "EUR", "SM": "EUR",
}

# 자주 쓰는 국가/지역 이름 -> 통화코드 (지오코딩 없이 바로 매칭)
NAME_TO_CURRENCY: dict[str, str] = {
    "한국": "KRW", "대한민국": "KRW", "korea": "KRW", "south korea": "KRW",
    "미국": "USD", "usa": "USD", "us": "USD", "united states": "USD", "america": "USD",
    "일본": "JPY", "japan": "JPY", "중국": "CNY", "china": "CNY",
    "홍콩": "HKD", "hong kong": "HKD", "대만": "TWD", "taiwan": "TWD",
    "마카오": "MOP", "macau": "MOP", "싱가포르": "SGD", "singapore": "SGD",
    "태국": "THB", "thailand": "THB", "베트남": "VND", "vietnam": "VND",
    "필리핀": "PHP", "philippines": "PHP", "말레이시아": "MYR", "malaysia": "MYR",
    "인도네시아": "IDR", "indonesia": "IDR", "인도": "INR", "india": "INR",
    "호주": "AUD", "australia": "AUD", "뉴질랜드": "NZD", "new zealand": "NZD",
    "캐나다": "CAD", "canada": "CAD", "멕시코": "MXN", "mexico": "MXN",
    "영국": "GBP", "uk": "GBP", "united kingdom": "GBP", "england": "GBP",
    "스위스": "CHF", "switzerland": "CHF", "튀르키예": "TRY", "터키": "TRY", "turkey": "TRY",
    "유럽": "EUR", "europe": "EUR", "독일": "EUR", "germany": "EUR", "프랑스": "EUR",
    "france": "EUR", "이탈리아": "EUR", "italy": "EUR", "스페인": "EUR", "spain": "EUR",
    "포르투갈": "EUR", "portugal": "EUR", "네덜란드": "EUR", "netherlands": "EUR",
    "오스트리아": "EUR", "austria": "EUR", "그리스": "EUR", "greece": "EUR",
    "몽골": "MNT", "mongolia": "MNT", "아랍에미리트": "AED", "uae": "AED", "두바이": "AED",
    "괌": "USD", "guam": "USD", "사이판": "USD", "saipan": "USD", "하와이": "USD", "hawaii": "USD",
}

# WMO 날씨 코드 -> 한국어 설명
WMO_CODES: dict[int, str] = {
    0: "맑음", 1: "대체로 맑음", 2: "부분적으로 흐림", 3: "흐림",
    45: "안개", 48: "서리 안개",
    51: "약한 이슬비", 53: "이슬비", 55: "강한 이슬비",
    56: "약한 어는 이슬비", 57: "강한 어는 이슬비",
    61: "약한 비", 63: "비", 65: "강한 비",
    66: "약한 어는 비", 67: "강한 어는 비",
    71: "약한 눈", 73: "눈", 75: "강한 눈", 77: "싸락눈",
    80: "약한 소나기", 81: "소나기", 82: "강한 소나기",
    85: "약한 눈 소나기", 86: "강한 눈 소나기",
    95: "뇌우", 96: "약한 우박을 동반한 뇌우", 99: "강한 우박을 동반한 뇌우",
}


def _wmo(code: int | None) -> str:
    if code is None:
        return "알 수 없음"
    return WMO_CODES.get(int(code), f"코드 {code}")


# --------------------------------------------------------------------------
# API 헬퍼
# --------------------------------------------------------------------------

async def _get_json(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    resp = await client.get(url, params=params, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


async def _fetch_rates(client: httpx.AsyncClient, base: str) -> dict:
    data = await _get_json(client, EXCHANGE_URL.format(base=base.upper()))
    if data.get("result") != "success":
        raise ValueError(f"환율 조회 실패 (base={base}): {data.get('error-type', 'unknown error')}")
    return data


# Open-Meteo 지오코딩이 한글명을 인식하지 못하는 도시 -> 영문명
KO_CITY_ALIASES: dict[str, str] = {
    "서울": "Seoul", "부산": "Busan", "인천": "Incheon", "대구": "Daegu", "대전": "Daejeon",
    "광주": "Gwangju", "울산": "Ulsan", "제주": "Jeju", "제주도": "Jeju", "강릉": "Gangneung",
    "경주": "Gyeongju", "여수": "Yeosu", "속초": "Sokcho", "전주": "Jeonju",
    "오사카": "Osaka", "후쿠오카": "Fukuoka", "삿포로": "Sapporo", "오키나와": "Naha",
    "다낭": "Da Nang", "나트랑": "Nha Trang", "하노이": "Hanoi", "호치민": "Ho Chi Minh City",
    "세부": "Cebu", "발리": "Denpasar", "푸켓": "Phuket", "치앙마이": "Chiang Mai",
    "타이베이": "Taipei", "상하이": "Shanghai", "베이징": "Beijing", "뉴욕": "New York",
    "로스앤젤레스": "Los Angeles", "엘에이": "Los Angeles", "런던": "London", "파리": "Paris",
    "로마": "Rome", "바르셀로나": "Barcelona", "시드니": "Sydney", "두바이": "Dubai",
}


async def _geocode(client: httpx.AsyncClient, name: str) -> dict:
    """도시/국가 이름을 좌표로 변환. 한글명 -> 영문 별칭 순으로 시도."""
    candidates = [name.strip()]
    alias = KO_CITY_ALIASES.get(name.strip())
    if alias:
        candidates.append(alias)
    for query in candidates:
        data = await _get_json(
            client, GEOCODE_URL,
            {"name": query, "count": 1, "language": "ko", "format": "json"},
        )
        results = data.get("results")
        if results:
            return results[0]
    raise ValueError(f"'{name}' 위치를 찾을 수 없습니다. 다른 표기(영문 도시명 등)로 시도해 보세요.")


async def _resolve_currency(client: httpx.AsyncClient, value: str) -> tuple[str, str | None]:
    """통화코드/국가명/도시명 -> (통화코드, 해석 설명)."""
    v = value.strip()
    key = v.lower()
    if key not in NAME_TO_CURRENCY and len(v) == 3 and v.isascii() and v.isalpha():
        return v.upper(), None
    if key in NAME_TO_CURRENCY:
        return NAME_TO_CURRENCY[key], f"'{v}' -> {NAME_TO_CURRENCY[key]}"
    place = await _geocode(client, v)
    cc = place.get("country_code", "").upper()
    cur = COUNTRY_TO_CURRENCY.get(cc)
    if not cur:
        raise ValueError(f"'{v}'({place.get('country', cc)})의 통화를 판별할 수 없습니다. 통화코드를 직접 입력하세요.")
    return cur, f"'{v}' -> {place.get('country', cc)} -> {cur}"


async def _fetch_weather(client: httpx.AsyncClient, place: dict, days: int) -> dict:
    params = {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_probability_max,precipitation_sum,wind_speed_10m_max,uv_index_max",
        "timezone": "auto",
        "forecast_days": days,
    }
    return await _get_json(client, FORECAST_URL, params)


def _place_label(place: dict) -> str:
    parts = [place.get("name"), place.get("admin1"), place.get("country")]
    seen, out = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return ", ".join(out)


def _format_weather(place: dict, w: dict) -> dict:
    cur = w.get("current", {})
    daily = w.get("daily", {})
    forecast = []
    for i, date in enumerate(daily.get("time", [])):
        forecast.append({
            "date": date,
            "weather": _wmo(daily["weather_code"][i]),
            "temp_min_c": daily["temperature_2m_min"][i],
            "temp_max_c": daily["temperature_2m_max"][i],
            "precip_probability_pct": daily["precipitation_probability_max"][i],
            "precip_sum_mm": daily["precipitation_sum"][i],
            "wind_max_kmh": daily["wind_speed_10m_max"][i],
            "uv_index_max": daily["uv_index_max"][i],
        })
    return {
        "location": _place_label(place),
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "timezone": w.get("timezone"),
        "current": {
            "time": cur.get("time"),
            "weather": _wmo(cur.get("weather_code")),
            "temperature_c": cur.get("temperature_2m"),
            "feels_like_c": cur.get("apparent_temperature"),
            "humidity_pct": cur.get("relative_humidity_2m"),
            "precipitation_mm": cur.get("precipitation"),
            "wind_kmh": cur.get("wind_speed_10m"),
        },
        "daily_forecast": forecast,
    }


# --------------------------------------------------------------------------
# 여행 점수 계산
# --------------------------------------------------------------------------

def _score_day(day: dict) -> tuple[float, list[str]]:
    """하루 날씨를 0~100점으로 평가."""
    score = 100.0
    notes: list[str] = []
    tmin, tmax = day["temp_min_c"], day["temp_max_c"]
    avg = (tmin + tmax) / 2 if tmin is not None and tmax is not None else None

    if avg is not None:
        if 15 <= avg <= 25:
            pass
        elif 10 <= avg < 15 or 25 < avg <= 28:
            score -= 10
        elif 5 <= avg < 10 or 28 < avg <= 32:
            score -= 25
            notes.append("쌀쌀함" if avg < 10 else "더움")
        else:
            score -= 40
            notes.append("추움" if avg < 5 else "무더위")

    pp = day.get("precip_probability_pct") or 0
    if pp >= 70:
        score -= 35
        notes.append(f"강수확률 {pp}%")
    elif pp >= 40:
        score -= 20
        notes.append(f"강수확률 {pp}%")
    elif pp >= 20:
        score -= 5

    wind = day.get("wind_max_kmh") or 0
    if wind >= 50:
        score -= 20
        notes.append(f"강풍 {wind}km/h")
    elif wind >= 30:
        score -= 8

    uv = day.get("uv_index_max") or 0
    if uv >= 8:
        notes.append(f"자외선 매우 강함(UV {uv})")

    return max(0.0, score), notes


def _grade(score: float) -> str:
    if score >= 85:
        return "매우 좋음"
    if score >= 70:
        return "좋음"
    if score >= 50:
        return "보통"
    if score >= 30:
        return "나쁨"
    return "매우 나쁨"


def _clothing_tip(tmin: float, tmax: float) -> str:
    avg = (tmin + tmax) / 2
    if avg >= 28:
        return "반팔·반바지, 통풍 잘 되는 옷, 모자·선크림"
    if avg >= 20:
        return "반팔 또는 얇은 긴팔, 일교차 대비 가벼운 겉옷"
    if avg >= 12:
        return "긴팔, 가디건이나 얇은 재킷"
    if avg >= 5:
        return "니트, 코트 또는 두꺼운 재킷"
    return "패딩, 목도리·장갑 등 방한용품"


# --------------------------------------------------------------------------
# MCP 도구
# --------------------------------------------------------------------------

@mcp.tool
async def get_exchange_rate(
    base: str = "USD",
    target: str | None = None,
    amount: float = 1.0,
) -> dict[str, Any]:
    """환율을 조회합니다.

    Args:
        base: 기준 통화. ISO 코드(USD, KRW) 또는 국가/도시 이름(미국, 일본, Paris).
        target: 대상 통화. 생략하면 주요 통화 목록을 반환합니다.
        amount: 환산할 금액 (기본 1).
    """
    async with httpx.AsyncClient() as client:
        base_code, base_note = await _resolve_currency(client, base)
        data = await _fetch_rates(client, base_code)
        rates: dict[str, float] = data["rates"]

        result: dict[str, Any] = {
            "base": base_code,
            "amount": amount,
            "last_updated": data.get("time_last_update_utc"),
            "next_update": data.get("time_next_update_utc"),
            "source": "open.er-api.com",
        }
        notes = [n for n in (base_note,) if n]

        if target:
            target_code, target_note = await _resolve_currency(client, target)
            if target_note:
                notes.append(target_note)
            if target_code not in rates:
                raise ValueError(f"지원하지 않는 통화코드입니다: {target_code}")
            rate = rates[target_code]
            result.update({
                "target": target_code,
                "rate": rate,
                "inverse_rate": round(1 / rate, 8) if rate else None,
                "converted": round(amount * rate, 4),
                "summary": f"{amount:,.2f} {base_code} = {amount * rate:,.4f} {target_code}",
            })
        else:
            majors = ["USD", "EUR", "JPY", "CNY", "GBP", "KRW", "HKD", "TWD",
                      "SGD", "THB", "VND", "AUD", "CAD", "CHF"]
            result["rates"] = {
                c: float(f"{amount * rates[c]:.6g}") for c in majors if c in rates and c != base_code
            }
        if notes:
            result["resolved"] = notes
        return result


@mcp.tool
async def get_weather(location: str, days: int = 3) -> dict[str, Any]:
    """도시 또는 국가의 현재 날씨와 일별 예보를 조회합니다.

    Args:
        location: 도시나 국가 이름 (예: 서울, 도쿄, Paris, 태국).
        days: 예보 일수 1~16 (기본 3).
    """
    days = max(1, min(16, int(days)))
    async with httpx.AsyncClient() as client:
        place = await _geocode(client, location)
        w = await _fetch_weather(client, place, days)
    return _format_weather(place, w)


@mcp.tool
async def analyze_travel_condition(
    destination: str,
    home_currency: str = "KRW",
    days: int = 5,
    budget: float | None = None,
) -> dict[str, Any]:
    """목적지의 날씨와 환율을 종합해 여행 환경을 분석합니다.

    Args:
        destination: 여행지 도시 또는 국가 (예: 도쿄, 방콕, Paris).
        home_currency: 출발지(본인) 통화 코드 또는 국가명 (기본 KRW).
        days: 분석할 여행 일수 1~16 (기본 5).
        budget: 본인 통화 기준 여행 예산. 주면 현지 통화로 환산합니다.
    """
    days = max(1, min(16, int(days)))
    async with httpx.AsyncClient() as client:
        place = await _geocode(client, destination)
        weather = _format_weather(place, await _fetch_weather(client, place, days))

        home_code, _ = await _resolve_currency(client, home_currency)
        cc = (place.get("country_code") or "").upper()
        local_code = COUNTRY_TO_CURRENCY.get(cc)
        exchange: dict[str, Any] = {"home_currency": home_code, "local_currency": local_code}
        if local_code is None:
            exchange["note"] = f"{place.get('country', cc)}의 통화를 판별하지 못해 환율 분석을 생략했습니다."
        elif local_code == home_code:
            exchange["note"] = "본인 통화와 현지 통화가 같아 환전이 필요 없습니다."
        else:
            data = await _fetch_rates(client, home_code)
            rates = data["rates"]
            usd_data = await _fetch_rates(client, "USD")
            rate = rates.get(local_code)
            if rate:
                # 체감하기 쉬운 단위로 표시 (예: 100엔 = 약 900원)
                unit = 1
                while (1 / rate) * unit < 1 and unit < 1_000_000:
                    unit *= 10
                exchange.update({
                    "rate": rate,
                    "per_local_unit": f"{unit:,} {local_code} ≈ {unit / rate:,.2f} {home_code}",
                    "examples": {
                        f"{amt:,} {home_code}": f"{amt * rate:,.2f} {local_code}"
                        for amt in (10_000, 50_000, 100_000)
                    } if home_code == "KRW" else {
                        f"{amt:,} {home_code}": f"{amt * rate:,.2f} {local_code}"
                        for amt in (10, 50, 100)
                    },
                    "usd_reference": {
                        f"1 USD in {home_code}": usd_data["rates"].get(home_code),
                        f"1 USD in {local_code}": usd_data["rates"].get(local_code),
                    },
                    "last_updated": data.get("time_last_update_utc"),
                })
                if budget:
                    exchange["budget"] = {
                        "home": f"{budget:,.0f} {home_code}",
                        "local": f"{budget * rate:,.2f} {local_code}",
                        "per_day_local": f"{budget * rate / days:,.2f} {local_code}",
                    }

    # 날씨 평가
    day_reports = []
    for d in weather["daily_forecast"]:
        s, notes = _score_day(d)
        day_reports.append({
            "date": d["date"],
            "weather": d["weather"],
            "temp": f"{d['temp_min_c']}~{d['temp_max_c']}°C",
            "score": round(s),
            "grade": _grade(s),
            "notes": notes,
        })
    scores = [r["score"] for r in day_reports]
    avg_score = sum(scores) / len(scores) if scores else 0
    best = max(day_reports, key=lambda r: r["score"]) if day_reports else None
    worst = min(day_reports, key=lambda r: r["score"]) if day_reports else None
    rainy_days = sum(1 for d in weather["daily_forecast"] if (d["precip_probability_pct"] or 0) >= 50)
    tmin = min(d["temp_min_c"] for d in weather["daily_forecast"])
    tmax = max(d["temp_max_c"] for d in weather["daily_forecast"])

    recommendations = [f"옷차림: {_clothing_tip(tmin, tmax)}"]
    if rainy_days:
        recommendations.append(f"{days}일 중 {rainy_days}일 비 가능성 높음 → 우산·실내 일정 준비")
    if tmax - tmin >= 12:
        recommendations.append(f"기간 중 기온차가 큼({tmin}~{tmax}°C) → 겹쳐 입기 좋은 옷")
    if any((d["uv_index_max"] or 0) >= 8 for d in weather["daily_forecast"]):
        recommendations.append("자외선 강함 → 선크림·선글라스")
    if best and worst and best["score"] - worst["score"] >= 20:
        recommendations.append(f"야외 일정은 {best['date']}에, 실내 일정은 {worst['date']}에 배치 추천")
    if exchange.get("rate"):
        recommendations.append(
            "환율 정보는 하루 1회 갱신되는 기준 환율이며, 실제 환전·카드 결제 시 수수료가 붙습니다."
        )

    summary = (
        f"{weather['location']} {days}일간 여행 날씨 점수 {avg_score:.0f}/100 ({_grade(avg_score)}). "
        f"기온 {tmin}~{tmax}°C, 비 올 가능성 높은 날 {rainy_days}일."
    )
    if exchange.get("per_local_unit"):
        summary += f" 환율: {exchange['per_local_unit']}."

    return {
        "destination": weather["location"],
        "summary": summary,
        "overall_weather_score": round(avg_score),
        "overall_grade": _grade(avg_score),
        "current_weather": weather["current"],
        "daily": day_reports,
        "best_day": best["date"] if best else None,
        "exchange": exchange,
        "recommendations": recommendations,
    }


# --------------------------------------------------------------------------
# 엔트리포인트
# --------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--http":
        port = int(sys.argv[2]) if len(sys.argv) >= 3 else 8000
        mcp.run(transport="http", host="127.0.0.1", port=port)
    else:
        mcp.run()
