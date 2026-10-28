"""课表核心逻辑：解析 ics、换算北京时间、按日期分组、生成网页。

这里只放"纯函数"（不联网、不读写文件），方便测试。
联网和写文件在 build.py 里。

TimeEdit 的字段用法和常规不同：
  LOCATION    = 课程名称
  DESCRIPTION = 课程类型和教室，例如 "Cours, Salle de classe (0.03)"，第二行是内部 ID
  SUMMARY     = 内部课程代码（不显示）
  DTSTART/END = UTC 时间
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from icalendar import Calendar

BEIJING = ZoneInfo("Asia/Shanghai")
WEEKDAYS = "一二三四五六日"

# 课程名中文翻译。出现新课时在这里补一行；没翻译的课会直接显示英文。
COURSE_NAMES_ZH = {
    "Strategy and business Diagnostic": "战略与商业诊断",
    "Sustainable Marketing": "可持续营销",
    "Luxury Marketing": "奢侈品营销",
    "Digital Marketing": "数字营销",
    "Introduction to Applied Research (IAR)": "应用研究导论",
    "International perspective on sustainability issues": "可持续发展问题的国际视角",
    "ANG : Speaking English in the Workplace": "职场英语口语",
}

# DESCRIPTION 里的地点类型
PLACE_KINDS_ZH = {
    "Salle de classe": "教室",
    "Amphitheatre": "阶梯教室",
    "Amphithéâtre": "阶梯教室",
}

# DESCRIPTION 里的课程类型；"Cours"（普通讲课）不显示
LESSON_TYPES_ZH = {
    "Cours": "",
    "Examen": "考试",
}


@dataclass(frozen=True)
class Lesson:
    start: datetime  # 带时区的时间
    end: datetime
    name: str
    room: str


def _as_utc(value) -> datetime:
    """把 ics 里的时间统一成带时区的 UTC 时间。"""
    if not isinstance(value, datetime):
        raise ValueError(f"不支持全天事件：{value!r}")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_lessons(ics_data: str | bytes) -> list[Lesson]:
    """解析 ics 文本，返回所有未取消的课程（不排序）。"""
    calendar = Calendar.from_ical(ics_data)
    lessons = []
    for event in calendar.walk("VEVENT"):
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        description = str(event.get("DESCRIPTION", ""))
        lessons.append(
            Lesson(
                start=_as_utc(event.decoded("DTSTART")),
                end=_as_utc(event.decoded("DTEND")),
                name=str(event.get("LOCATION", "")).strip(),
                room=description.splitlines()[0].strip() if description else "",
            )
        )
    return lessons


def course_name_zh(name: str) -> str | None:
    """课程的中文名；没有翻译时返回 None。"""
    return COURSE_NAMES_ZH.get(name)


def untranslated_courses(lessons: list[Lesson]) -> list[str]:
    """还没有中文翻译的课程名（去重、排序），用于提醒补翻译。"""
    return sorted({lesson.name for lesson in lessons if course_name_zh(lesson.name) is None})


def _translate_place(place: str) -> str:
    """"Salle de classe (0.08)" → "教室 0.08"；认不出的原样返回。"""
    match = re.fullmatch(r"(.+?)\s*\((.+)\)", place)
    if match and match.group(1) in PLACE_KINDS_ZH:
        return f"{PLACE_KINDS_ZH[match.group(1)]} {match.group(2)}"
    return place


def room_zh(room: str) -> str:
    """把 "Cours, Salle de classe (0.08)" 翻译成 "教室 0.08"。

    课程类型不是普通讲课时放在前面，例如 "考试 · 教室 0.08"。
    """
    kind, sep, place = room.partition(",")
    if not sep:
        return _translate_place(room.strip())
    kind = kind.strip()
    place = _translate_place(place.strip())
    kind_zh = LESSON_TYPES_ZH.get(kind, kind)
    return f"{kind_zh} · {place}" if kind_zh else place


def beijing_date(moment: datetime) -> date:
    return moment.astimezone(BEIJING).date()


def upcoming(lessons: list[Lesson], now: datetime) -> list[Lesson]:
    """从北京时间的"今天"开始的课程（包括今天已经上完的），按开始时间排序。"""
    today = beijing_date(now)
    kept = [lesson for lesson in lessons if beijing_date(lesson.start) >= today]
    return sorted(kept, key=lambda lesson: lesson.start)


def group_by_day(lessons: list[Lesson]) -> list[tuple[date, list[Lesson]]]:
    """按北京时间的日期分组。输入需已按时间排序。"""
    groups: list[tuple[date, list[Lesson]]] = []
    for lesson in lessons:
        day = beijing_date(lesson.start)
        if groups and groups[-1][0] == day:
            groups[-1][1].append(lesson)
        else:
            groups.append((day, [lesson]))
    return groups


def format_time_range(lesson: Lesson) -> str:
    """例如 "09:00 – 11:00"；跨过北京时间午夜时写成 "23:15 – 次日 02:30"。"""
    start = lesson.start.astimezone(BEIJING)
    end = lesson.end.astimezone(BEIJING)
    end_text = end.strftime("%H:%M")
    if end.date() > start.date():
        end_text = "次日 " + end_text
    return f"{start:%H:%M} – {end_text}"


def format_day(day: date, today: date) -> str:
    """例如 "11月2日 周一 · 今天"。"""
    text = f"{day.month}月{day.day}日 周{WEEKDAYS[day.weekday()]}"
    if day == today:
        text += " · 今天"
    elif day == today + timedelta(days=1):
        text += " · 明天"
    return text


PAGE_STYLE = """
body { font-family: -apple-system, "PingFang SC", "Noto Sans CJK SC", sans-serif;
       margin: 0 auto; max-width: 640px; padding: 16px; color: #222; background: #fff;
       line-height: 1.5; }
h1 { font-size: 22px; margin: 0 0 4px; }
.updated { color: #666; font-size: 14px; margin: 0 0 16px; }
h2 { font-size: 17px; margin: 20px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #ddd; }
.lesson { padding: 10px 12px; margin-bottom: 8px; background: #f5f5f7; border-radius: 8px; }
.time { font-weight: bold; }
.name { font-size: 16px; }
.en { color: #777; font-size: 12px; }
.room { color: #555; font-size: 14px; }
.empty { color: #666; }
"""


def render_course_name(name: str) -> str:
    """中文名 + 小字英文原名；没有翻译时只显示英文。返回 HTML。"""
    zh = course_name_zh(name)
    if zh is None:
        return escape(name)
    return f'{escape(zh)} <small class="en">({escape(name)})</small>'


def render_html(lessons: list[Lesson], now: datetime) -> str:
    """生成完整网页。lessons 需已经过 upcoming() 过滤排序。"""
    today = beijing_date(now)
    updated = now.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M")

    parts = []
    for day, day_lessons in group_by_day(lessons):
        parts.append(f"<h2>{escape(format_day(day, today))}</h2>")
        for lesson in day_lessons:
            parts.append(
                '<div class="lesson">'
                f'<div class="time">{escape(format_time_range(lesson))}</div>'
                f'<div class="name">{render_course_name(lesson.name)}</div>'
                f'<div class="room">{escape(room_zh(lesson.room))}</div>'
                "</div>"
            )
    if not parts:
        parts.append('<p class="empty">近期没有课 🎉</p>')

    body = "\n".join(parts)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kevin 的课表</title>
<style>{PAGE_STYLE}</style>
</head>
<body>
<h1>Kevin 的课表</h1>
<p class="updated">时间均为北京时间 · 最后更新：{updated}</p>
{body}
</body>
</html>
"""


def build_page(ics_data: str | bytes, now: datetime) -> str:
    """从 ics 文本一步生成网页。"""
    return render_html(upcoming(parse_lessons(ics_data), now), now)
