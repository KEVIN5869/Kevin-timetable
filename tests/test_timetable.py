"""timetable.py 的测试。

样例 ics 里的课程（北京时间 = UTC+8），"现在"固定为北京时间 2026-11-02 周一 12:00：
  A 11月1日 22:00–23:59  昨天，不显示
  G 11月2日 00:00–01:00  今天零点整，显示
  B 11月2日 09:00–11:00  今天已上完，仍显示；课程名在 ics 里被折行
  C 11月2日 23:15–次日 02:30  跨午夜
  D 11月3日 00:30–02:00  法国还是 11月2日晚上，北京已是 11月3日
  F 11月4日  已取消，不显示
  E 11月5日 16:00–18:00  在文件里排第一，用来检查排序；名字含 HTML 特殊字符
"""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from timetable import (
    COURSE_NAMES_ZH,
    build_page,
    course_name_zh,
    format_day,
    format_time_range,
    group_by_day,
    parse_lessons,
    render_course_name,
    render_html,
    room_zh,
    untranslated_courses,
    upcoming,
)

SAMPLE = (Path(__file__).parent / "fixtures" / "sample.ics").read_bytes()
NOW = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)  # 北京时间 11月2日 12:00


@pytest.fixture
def lessons():
    return parse_lessons(SAMPLE)


def by_name(lessons, name):
    return next(lesson for lesson in lessons if lesson.name == name)


# ---------- 解析 ----------

def test_parse_skips_cancelled_lessons(lessons):
    names = {lesson.name for lesson in lessons}
    assert "Cancelled Course" not in names
    assert len(lessons) == 6


def test_parse_reads_timeedit_fields(lessons):
    lesson = by_name(lessons, "Strategy and business Diagnostic")  # 折行已拼回
    assert lesson.room == "Cours, Salle de classe (0.03)"  # 逗号已还原，ID 行已去掉
    assert lesson.start == datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)
    assert lesson.end == datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc)


def test_parse_accepts_text_input():
    assert len(parse_lessons(SAMPLE.decode("utf-8"))) == 6


# ---------- 过滤与排序 ----------

def test_upcoming_starts_from_beijing_today_and_is_sorted(lessons):
    names = [lesson.name for lesson in upcoming(lessons, NOW)]
    assert names == [
        "Midnight Course",
        "Strategy and business Diagnostic",
        "ANG : Speaking English in the Workplace",
        "Digital Marketing",
        "R&D <Lab>",
    ]


def test_upcoming_uses_beijing_date_not_utc_date(lessons):
    # UTC 11月1日 16:30 = 北京时间 11月2日 00:30，"今天"已经是 11月2日
    now = datetime(2026, 11, 1, 16, 30, tzinfo=timezone.utc)
    names = [lesson.name for lesson in upcoming(lessons, now)]
    assert "Yesterday Course" not in names
    assert "Midnight Course" in names


# ---------- 分组 ----------

def test_group_by_beijing_day(lessons):
    groups = group_by_day(upcoming(lessons, NOW))
    assert [(day, [lesson.name for lesson in items]) for day, items in groups] == [
        (date(2026, 11, 2), [
            "Midnight Course",
            "Strategy and business Diagnostic",
            "ANG : Speaking English in the Workplace",
        ]),
        (date(2026, 11, 3), ["Digital Marketing"]),
        (date(2026, 11, 5), ["R&D <Lab>"]),
    ]


def test_group_by_day_empty():
    assert group_by_day([]) == []


# ---------- 格式化 ----------

def test_time_range_in_beijing_time(lessons):
    assert format_time_range(by_name(lessons, "Strategy and business Diagnostic")) == "09:00 – 11:00"


def test_time_range_crossing_midnight(lessons):
    lesson = by_name(lessons, "ANG : Speaking English in the Workplace")
    assert format_time_range(lesson) == "23:15 – 次日 02:30"


def test_format_day_labels():
    today = date(2026, 11, 2)
    assert format_day(date(2026, 11, 2), today) == "11月2日 周一 · 今天"
    assert format_day(date(2026, 11, 3), today) == "11月3日 周二 · 明天"
    assert format_day(date(2026, 11, 8), today) == "11月8日 周日"


# ---------- 网页 ----------

def test_page_shows_lessons_and_update_time():
    page = build_page(SAMPLE, NOW)
    assert "最后更新：2026-11-02 12:00" in page
    assert "11月2日 周一 · 今天" in page
    assert "11月3日 周二 · 明天" in page
    assert "23:15 – 次日 02:30" in page
    assert "教室 0.03" in page
    assert "Yesterday Course" not in page
    assert "Cancelled Course" not in page


def test_page_hides_internal_codes_and_ids():
    page = build_page(SAMPLE, NOW)
    assert "CODE_" not in page
    assert "ID 2" not in page


def test_page_escapes_html():
    page = build_page(SAMPLE, NOW)
    assert "R&amp;D &lt;Lab&gt;" in page
    assert "<Lab>" not in page


def test_page_is_mobile_friendly():
    page = build_page(SAMPLE, NOW)
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in page
    assert '<meta charset="utf-8">' in page


def test_page_when_no_lessons():
    page = render_html([], NOW)
    assert "近期没有课" in page
    assert "最后更新：2026-11-02 12:00" in page


# ---------- 中文翻译 ----------

@pytest.mark.parametrize("english, chinese", [
    ("Strategy and business Diagnostic", "战略与商业诊断"),
    ("Sustainable Marketing", "可持续营销"),
    ("Luxury Marketing", "奢侈品营销"),
    ("Digital Marketing", "数字营销"),
    ("Introduction to Applied Research (IAR)", "应用研究导论"),
    ("International perspective on sustainability issues", "可持续发展问题的国际视角"),
    ("ANG : Speaking English in the Workplace", "职场英语口语"),
])
def test_course_names_are_translated(english, chinese):
    assert course_name_zh(english) == chinese


def test_all_seven_courses_have_translations():
    assert len(COURSE_NAMES_ZH) == 7


def test_unknown_course_has_no_translation():
    assert course_name_zh("Brand New Course") is None


def test_course_name_shows_chinese_with_small_english():
    html = render_course_name("Digital Marketing")
    assert html == '数字营销 <small class="en">(Digital Marketing)</small>'


def test_untranslated_course_shows_english_only():
    assert render_course_name("R&D <Lab>") == "R&amp;D &lt;Lab&gt;"


def test_untranslated_courses_lists_missing_names(lessons):
    assert untranslated_courses(lessons) == [
        "Midnight Course",
        "R&D <Lab>",
        "Yesterday Course",
    ]


@pytest.mark.parametrize("room, expected", [
    ("Cours, Salle de classe (0.08)", "教室 0.08"),
    ("Cours, Amphitheatre (A)", "阶梯教室 A"),
    ("Examen, Salle de classe (1.13)", "考试 · 教室 1.13"),
    ("TD, Salle de classe (2.04)", "TD · 教室 2.04"),          # 不认识的类型原样保留
    ("Cours, Gymnase (B)", "Gymnase (B)"),                     # 不认识的地点原样保留
    ("Salle de classe (0.01)", "教室 0.01"),                    # 没有类型
    ("", ""),
])
def test_room_translation(room, expected):
    assert room_zh(room) == expected


def test_page_shows_translated_names():
    page = build_page(SAMPLE, NOW)
    assert '战略与商业诊断 <small class="en">(Strategy and business Diagnostic)</small>' in page
    assert "阶梯教室 A" in page
    assert "Cours," not in page
