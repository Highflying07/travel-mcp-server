# travel-info MCP Server

[FastMCP](https://gofastmcp.com)로 만든 단일 파일 MCP 서버입니다. 환율, 날씨, 그리고 둘을 합친 여행 환경 분석을 제공합니다.

## 도구

| 도구 | 설명 | 주요 인자 |
|---|---|---|
| `get_exchange_rate` | 환율 조회 | `base`, `target`(선택), `amount` |
| `get_weather` | 현재 날씨 + 일별 예보 (1~16일) | `location`, `days` |
| `analyze_travel_condition` | 날씨 점수, 환율, 예산 환산, 옷차림·일정 추천 | `destination`, `home_currency`(기본 KRW), `days`, `budget`(선택) |

통화는 ISO 코드(`JPY`)뿐 아니라 국가명(`일본`, `Japan`)이나 도시명(`Paris`)으로도 지정할 수 있습니다.

## 데이터 출처 (API 키 불필요)

- 환율: [open.er-api.com](https://open.er-api.com/v6/latest/USD) (하루 1회 갱신)
- 도시 좌표: [Open-Meteo Geocoding](https://open-meteo.com/en/docs/geocoding-api)
- 날씨: [Open-Meteo Forecast](https://open-meteo.com/en/docs)

## 설치

```bash
pip install -r requirements.txt
```

`truststore`는 회사망처럼 TLS 검사 프록시가 있는 환경에서 SSL 오류를 막기 위해 OS 인증서 저장소를 사용합니다.

## 실행

```bash
# stdio (Claude Desktop / Claude Code)
python travel_mcp_server.py

# Streamable HTTP
python travel_mcp_server.py --http 8000
```

## Claude Desktop 등록

`claude_desktop_config.json`에 추가:

```json
{
  "mcpServers": {
    "travel-info": {
      "command": "python",
      "args": ["C:\\path\\to\\travel_mcp_server.py"],
      "env": { "PYTHONIOENCODING": "utf-8" }
    }
  }
}
```

## Claude Code 등록

```bash
claude mcp add travel-info -- python /path/to/travel_mcp_server.py
```
