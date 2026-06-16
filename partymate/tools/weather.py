"""
天气查询工具 — 使用 wttr.in API

可查询任意城市的实时天气、未来预报、日出日落等。
wttr.in 在国内外均可访问，无需 API Key。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

WTTR_IN_BASE = "https://wttr.in"


def _parse_wttr_json(raw: dict[str, Any]) -> str:
    """将 wttr.in 返回的 JSON 解析为简明中文天气文本。"""
    parts: list[str] = []

    current = raw.get("current_condition", [{}])[0]
    nearest = raw.get("nearest_area", [{}])[0]

    # 城市 & 国家
    city = nearest.get("areaName", [{}])[0].get("value", "未知")
    region = nearest.get("region", [{}])[0].get("value", "")
    country = nearest.get("country", [{}])[0].get("value", "未知")
    loc = city
    if region and region != city:
        loc += f"（{region}）"
    loc += f"，{country}"

    # 当前天气
    temp = current.get("temp_C", "?")
    feels = current.get("FeelsLikeC", "?")
    humidity = current.get("humidity", "?")
    desc = current.get("weatherDesc", [{}])[0].get("value", "未知")
    wind = current.get("windspeedKmph", "?")
    wind_dir = current.get("winddir16Point", "?")
    visibility = current.get("visibility", "?")
    pressure = current.get("pressure", "?")
    obs_time = current.get("observation_time", "")

    parts.append(f"📍 {loc}")
    parts.append(f"🕒 数据更新时间（UTC）：{obs_time}")
    parts.append(f"🌡️ 当前温度：{temp}°C（体感 {feels}°C）")
    parts.append(f"☁️ 天气状况：{desc}")
    parts.append(f"💧 湿度：{humidity}%")
    parts.append(f"🌬️ 风速：{wind} km/h（{wind_dir}）")
    parts.append(f"👁️ 能见度：{visibility} km")
    parts.append(f"🔽 气压：{pressure} hPa")

    # 未来预报（接下来 3 天）
    forecast = raw.get("weather", [])
    if forecast:
        parts.append("")
        parts.append("📅 未来天气预报：")
        for day in forecast:
            date = day.get("date", "?")
            avg = day.get("avgtempC", "?")
            max_t = day.get("maxtempC", "?")
            min_t = day.get("mintempC", "?")
            hourly = day.get("hourly", [])
            # 取中午时分（第 4 个条目，约 12:00）的描述作为白天天气概况
            noon = hourly[3] if len(hourly) > 3 else hourly[0] if hourly else {}
            noon_desc = noon.get("weatherDesc", [{}])[0].get("value", "")
            chance_rain = noon.get("chanceofrain", "?")
            parts.append(f"  - {date}：{noon_desc}，均温 {avg}°C（{min_t}~{max_t}°C），降雨概率 {chance_rain}%")

    # 日出日落
    astro = forecast[0].get("astronomy", [{}])[0] if forecast else {}
    if astro:
        parts.append("")
        parts.append(f"🌅 日出：{astro.get('sunrise', '?')}  🌇 日落：{astro.get('sunset', '?')}")
        parts.append(f"🌙 月相：{astro.get('moon_phase', '?')}（照亮 {astro.get('moon_illumination', '?')}%）")

    return "\n".join(parts)


async def get_weather(city: str, days: int = 3) -> str:
    """
    查询指定城市的实时天气和未来预报。

    Args:
        city: 城市名（中文或英文均可，如 "贵阳"、"Guiyang"、"上海"）
        days: 预报天数，默认为 3

    Returns:
        格式化天气文本
    """
    url = f"{WTTR_IN_BASE}/{city}"
    params = {
        "format": "j1",
        "lang": "zh",
    }
    if days and days > 0:
        params["days"] = str(days)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            raw: dict[str, Any] = resp.json()
            return _parse_wttr_json(raw)
    except httpx.TimeoutException:
        return json.dumps({"error": "天气查询超时，请稍后再试"}, ensure_ascii=False)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"天气服务返回错误: HTTP {e.response.status_code}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"天气查询失败: {str(e)}"}, ensure_ascii=False)