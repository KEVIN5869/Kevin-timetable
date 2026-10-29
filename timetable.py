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
from pathlib import Path
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


def week_start(day: date) -> date:
    """这一天所在周的周一。"""
    return day - timedelta(days=day.weekday())


Week = tuple[date, list[tuple[date, list[Lesson]]]]  # (周一, [(日期, 课程)])


def group_by_week(lessons: list[Lesson], now: datetime) -> list[Week]:
    """按北京时间的周（周一到周日）分组，每周里再按日期分组。

    周是连续的：中间没课的周也会保留（内容为空）。
    范围至少覆盖"本周"和"下周"，这样网页过了周日也总能翻到新的一周。
    """
    ordered = sorted(lessons, key=lambda lesson: lesson.start)
    this_week = week_start(beijing_date(now))
    first = this_week
    last = this_week + timedelta(weeks=1)
    if ordered:
        first = min(first, week_start(beijing_date(ordered[0].start)))
        last = max(last, week_start(beijing_date(ordered[-1].start)))

    days_by_week: dict[date, list[tuple[date, list[Lesson]]]] = {}
    for day, day_lessons in group_by_day(ordered):
        days_by_week.setdefault(week_start(day), []).append((day, day_lessons))

    weeks = []
    monday = first
    while monday <= last:
        weeks.append((monday, days_by_week.get(monday, [])))
        monday += timedelta(weeks=1)
    return weeks


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


def format_day(day: date) -> str:
    """例如 "11月2日 周一"。"今天/明天"由网页里的脚本实时标注。"""
    return f"{day.month}月{day.day}日 周{WEEKDAYS[day.weekday()]}"


def format_week_range(monday: date) -> str:
    """例如 "10月26日 – 11月1日"。"""
    sunday = monday + timedelta(days=6)
    return f"{monday.month}月{monday.day}日 – {sunday.month}月{sunday.day}日"


def epoch_ms(moment: datetime) -> int:
    """给网页脚本用的时间戳（毫秒）。"""
    return int(moment.timestamp() * 1000)


# 每门课一种颜色：(卡片底色, 标题文字色, 次要文字色)
COLORS = {
    "purple": ("#EEEDFE", "#3C3489", "#534AB7"),
    "teal": ("#E1F5EE", "#085041", "#0F6E56"),
    "pink": ("#FBEAF0", "#72243E", "#993556"),
    "blue": ("#E6F1FB", "#0C447C", "#185FA5"),
    "amber": ("#FAEEDA", "#633806", "#854F0B"),
    "coral": ("#FAECE7", "#712B13", "#993C1D"),
    "slate": ("#ECEFF5", "#2B3A55", "#4A5B7A"),
    "gray": ("#F1EFE8", "#2C2C2A", "#5F5E5A"),  # 没登记颜色的新课
}

COURSE_COLORS = {
    "Strategy and business Diagnostic": "purple",
    "Sustainable Marketing": "teal",
    "Luxury Marketing": "pink",
    "Digital Marketing": "blue",
    "Introduction to Applied Research (IAR)": "amber",
    "ANG : Speaking English in the Workplace": "coral",
    "International perspective on sustainability issues": "slate",
}


def course_color(name: str) -> str:
    return COURSE_COLORS.get(name, "gray")


def color_styles() -> str:
    rules = []
    for key, (background, title, subtitle) in COLORS.items():
        rules.append(
            f".c-{key} {{ background: {background}; }}\n"
            f".c-{key} .time, .c-{key} .name {{ color: {title}; }}\n"
            f".c-{key} .room, .c-{key} .en {{ color: {subtitle}; }}"
        )
    return "\n".join(rules)


PAGE_STYLE = """
[hidden] { display: none !important; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
       margin: 0 auto; max-width: 560px; padding: 20px 16px 32px; color: #2C2C2A;
       background: #FFFBF6; line-height: 1.5; -webkit-text-size-adjust: 100%; }
h1 { font-size: 22px; margin: 0; }
.heart { color: #D4537E; }
.updated { color: #888780; font-size: 12px; margin: 2px 0 16px; }
.updated.is-stale { color: #854F0B; background: #FAEEDA; font-weight: 600;
                    display: inline-block; padding: 2px 10px; border-radius: 10px; }

.pager { display: flex; align-items: center; justify-content: space-between; gap: 8px;
         background: #EEEDFE; border-radius: 16px; padding: 8px 10px; margin: 0 0 10px; }
.pager button { width: 36px; height: 36px; border: none; border-radius: 50%; background: #fff;
                color: #534AB7; font-size: 22px; line-height: 1; cursor: pointer;
                box-shadow: 0 1px 3px rgba(60, 52, 137, 0.15); }
.pager button:disabled { opacity: 0.35; box-shadow: none; cursor: default; }
.pager-text { text-align: center; }
.week-label { font-weight: 600; color: #3C3489; }
.week-range { font-size: 12px; color: #534AB7; }
.back { display: block; margin: 0 auto 10px; padding: 4px 14px; font-size: 13px;
        border: 1px solid #ED93B1; border-radius: 14px; background: #fff; color: #993556; }

.week-title { font-size: 16px; color: #534AB7; margin: 24px 0 4px; }
.js .week-title { display: none; }
h3 { display: flex; align-items: center; gap: 8px; font-size: 15px; margin: 18px 0 8px; }
.day-tag { font-size: 11px; font-weight: normal; padding: 1px 8px; border-radius: 10px; }
.day-tag[data-label="今天"] { background: #FBEAF0; color: #993556; }
.day-tag[data-label="明天"] { background: #E6F1FB; color: #0C447C; }

.lesson { padding: 10px 12px; margin-bottom: 8px; border-radius: 14px; border: 2px solid transparent; }
.top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.time { font-weight: 600; }
.name { font-weight: 600; font-size: 15px; margin-top: 2px; }
.en { font-weight: normal; font-size: 11px; }
.room { font-size: 13px; margin-top: 2px; }
.room::before { content: "📍 "; }
.room:empty::before { content: ""; }

.now-tag { display: none; background: #22A447; color: #fff; font-size: 11px; font-weight: 600;
           padding: 1px 9px; border-radius: 10px; white-space: nowrap; }
.lesson.is-now { border-color: #22A447; }
.lesson.is-now .now-tag { display: inline-block; }
.lesson.is-past { opacity: 0.45; }

.empty { text-align: center; color: #888780; padding: 28px 0; margin: 12px 0;
         border: 2px dashed #E5E1D8; border-radius: 16px; }
footer { text-align: center; color: #B4B2A9; font-size: 12px; margin-top: 28px; }
""" + color_styles()

SCRIPT_PATH = Path(__file__).parent / "static" / "app.js"


def render_course_name(name: str) -> str:
    """中文名 + 小字英文原名；没有翻译时只显示英文。返回 HTML。"""
    zh = course_name_zh(name)
    if zh is None:
        return escape(name)
    return f'{escape(zh)} <small class="en">({escape(name)})</small>'


def render_lesson(lesson: Lesson) -> str:
    return (
        f'<article class="lesson c-{course_color(lesson.name)}" data-start="{epoch_ms(lesson.start)}" data-end="{epoch_ms(lesson.end)}">'
        '<div class="top">'
        f'<span class="time">{escape(format_time_range(lesson))}</span>'
        '<span class="now-tag">● NOW</span>'
        "</div>"
        f'<div class="name">{render_course_name(lesson.name)}</div>'
        f'<div class="room">{escape(room_zh(lesson.room))}</div>'
        "</article>"
    )


def render_week(monday: date, days: list[tuple[date, list[Lesson]]]) -> str:
    week_range = escape(format_week_range(monday))
    parts = [
        f'<section class="week" data-week="{monday.isoformat()}" data-range="{week_range}">',
        f'<h2 class="week-title">{week_range}</h2>',
    ]
    for day, day_lessons in days:
        parts.append(f'<div class="day" data-date="{day.isoformat()}">')
        parts.append(f'<h3>{escape(format_day(day))} <span class="day-tag"></span></h3>')
        parts.extend(render_lesson(lesson) for lesson in day_lessons)
        parts.append("</div>")
    if not days:
        parts.append('<p class="empty">这周没有课 🎉</p>')
    parts.append("</section>")
    return "\n".join(parts)


def render_html(lessons: list[Lesson], now: datetime) -> str:
    """生成完整网页：包含所有周，网页脚本负责显示本周和翻页。"""
    updated = now.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M")
    body = "\n".join(render_week(monday, days) for monday, days in group_by_week(lessons, now))
    script = SCRIPT_PATH.read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kevin 的课表</title>
<style>{PAGE_STYLE}</style>
</head>
<body>
<h1>Kevin 的课表 <span class="heart">♡</span></h1>
<p class="updated" data-updated="{epoch_ms(now)}">时间均为北京时间 · 最后更新：{updated}<span class="stale-note" hidden> · 课表可能不是最新</span></p>
<nav class="pager" hidden>
<button type="button" class="prev" aria-label="上一周">‹</button>
<div class="pager-text"><div class="week-label"></div><div class="week-range"></div></div>
<button type="button" class="next" aria-label="下一周">›</button>
</nav>
<button type="button" class="back" hidden>回到本周</button>
<main>
{body}
</main>
<footer>每 20 分钟自动更新 ♡</footer>
<script>
{script}
</script>
</body>
</html>
"""


def build_page(ics_data: str | bytes, now: datetime) -> str:
    """从 ics 文本一步生成网页。"""
    return render_html(parse_lessons(ics_data), now)
