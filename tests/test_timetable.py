"""timetable.py 的测试。

样例 ics 里的课程（北京时间 = UTC+8），"现在"固定为北京时间 2026-11-02 周一 12:00：
  A 11月1日 22:00–23:59  周日，属于上一周（10月26日那周）
  G 11月2日 00:00–01:00  周一零点整，属于本周
  B 11月2日 09:00–11:00  课程名在 ics 里被折行
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
    format_week_range,
    group_by_day,
    group_by_week,
    parse_lessons,
    render_course_name,
    render_html,
    room_zh,
    untranslated_courses,
    week_start,
)
from timetable import Lesson

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


# ---------- 分组 ----------

def week_names(weeks):
    return [
        (monday, [(day, [lesson.name for lesson in items]) for day, items in days])
        for monday, days in weeks
    ]


def test_group_by_beijing_day(lessons):
    groups = group_by_day(sorted(lessons, key=lambda lesson: lesson.start))
    assert [(day, [lesson.name for lesson in items]) for day, items in groups] == [
        (date(2026, 11, 1), ["Yesterday Course"]),
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


def test_week_start_is_monday():
    assert week_start(date(2026, 11, 2)) == date(2026, 11, 2)   # 周一
    assert week_start(date(2026, 11, 5)) == date(2026, 11, 2)   # 周四
    assert week_start(date(2026, 11, 8)) == date(2026, 11, 2)   # 周日
    assert week_start(date(2026, 11, 1)) == date(2026, 10, 26)  # 周日，跨月


def test_group_by_week_uses_beijing_dates_and_is_sorted(lessons):
    # 周日 23:59 的课在上一周，周一 00:00 的课在本周；本周后面还有一个空的"下周"
    assert week_names(group_by_week(lessons, NOW)) == [
        (date(2026, 10, 26), [(date(2026, 11, 1), ["Yesterday Course"])]),
        (date(2026, 11, 2), [
            (date(2026, 11, 2), [
                "Midnight Course",
                "Strategy and business Diagnostic",
                "ANG : Speaking English in the Workplace",
            ]),
            (date(2026, 11, 3), ["Digital Marketing"]),
            (date(2026, 11, 5), ["R&D <Lab>"]),
        ]),
        (date(2026, 11, 9), []),
    ]


def make_lesson(name, iso_start):
    start = datetime.fromisoformat(iso_start)
    return Lesson(start=start, end=start, name=name, room="")


def test_group_by_week_keeps_empty_weeks_in_between():
    lessons = [
        make_lesson("Week 1", "2026-11-03T08:00:00+00:00"),
        make_lesson("Week 3", "2026-11-17T08:00:00+00:00"),
    ]
    weeks = group_by_week(lessons, NOW)
    assert [monday for monday, _ in weeks] == [
        date(2026, 11, 2), date(2026, 11, 9), date(2026, 11, 16),
    ]
    assert weeks[1][1] == []


def test_group_by_week_always_includes_this_and_next_week():
    # 课都在很久以前，也要有本周和下周，网页才能显示"这周没有课"
    lessons = [make_lesson("Old", "2026-10-20T08:00:00+00:00")]
    mondays = [monday for monday, _ in group_by_week(lessons, NOW)]
    assert mondays[0] == date(2026, 10, 19)
    assert mondays[-2:] == [date(2026, 11, 2), date(2026, 11, 9)]
    assert len(mondays) == 4


def test_group_by_week_without_lessons():
    assert group_by_week([], NOW) == [(date(2026, 11, 2), []), (date(2026, 11, 9), [])]


# ---------- 格式化 ----------

def test_time_range_in_beijing_time(lessons):
    assert format_time_range(by_name(lessons, "Strategy and business Diagnostic")) == "09:00 – 11:00"


def test_time_range_crossing_midnight(lessons):
    lesson = by_name(lessons, "ANG : Speaking English in the Workplace")
    assert format_time_range(lesson) == "23:15 – 次日 02:30"


def test_format_day():
    assert format_day(date(2026, 11, 2)) == "11月2日 周一"
    assert format_day(date(2026, 11, 8)) == "11月8日 周日"


def test_format_week_range_across_months():
    assert format_week_range(date(2026, 10, 26)) == "10月26日 – 11月1日"


# ---------- 网页 ----------

def test_page_shows_lessons_and_update_time():
    page = build_page(SAMPLE, NOW)
    assert "最后更新：2026-11-02 12:00" in page
    assert "11月2日 周一" in page
    assert "23:15 – 次日 02:30" in page
    assert "教室 0.03" in page
    assert "Cancelled Course" not in page


def test_page_has_one_section_per_week():
    page = build_page(SAMPLE, NOW)
    assert page.count('<section class="week"') == 3
    assert 'data-week="2026-10-26" data-range="10月26日 – 11月1日"' in page
    assert 'data-week="2026-11-09"' in page
    assert '<div class="day" data-date="2026-11-03">' in page


def test_page_marks_lesson_times_for_the_script():
    page = build_page(SAMPLE, NOW)
    # B: 2026-11-02 01:00–03:00 UTC
    assert 'data-start="1793581200000" data-end="1793588400000"' in page


def test_page_includes_script_and_pager():
    page = build_page(SAMPLE, NOW)
    assert "function pickWeekIndex" in page
    assert 'class="prev"' in page and 'class="next"' in page
    assert "回到本周" in page


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
    assert page.count("这周没有课") == 2
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


def test_hidden_attribute_always_hides():
    # 按钮等元素有自己的 display 样式，必须保证 hidden 仍然能把它们藏起来
    assert "[hidden] { display: none !important; }" in build_page(SAMPLE, NOW)


def test_each_lesson_has_hidden_now_tag():
    page = build_page(SAMPLE, NOW)
    assert page.count('<span class="now-tag">● NOW</span>') == 6
    assert ".lesson.is-now .now-tag { display: inline-block; }" in page
    assert ".lesson.is-past {" in page


# ---------- 配色 ----------

from timetable import COLORS, COURSE_COLORS, course_color  # noqa: E402


def test_every_translated_course_has_its_own_color():
    assert set(COURSE_COLORS) == set(COURSE_NAMES_ZH)
    assert len(set(COURSE_COLORS.values())) == len(COURSE_COLORS)  # 颜色互不相同
    assert all(color in COLORS for color in COURSE_COLORS.values())


def test_unknown_course_is_gray():
    assert course_color("Brand New Course") == "gray"


def test_cards_use_course_colors():
    page = build_page(SAMPLE, NOW)
    assert '<article class="lesson c-purple"' in page   # Strategy and business Diagnostic
    assert '<article class="lesson c-blue"' in page     # Digital Marketing
    assert '<article class="lesson c-gray"' in page     # 未登记的课
    for key in COLORS:
        assert f".c-{key} {{ background:" in page


def test_day_tags_have_colors_for_today_and_tomorrow():
    page = build_page(SAMPLE, NOW)
    assert '.day-tag[data-label="今天"]' in page
    assert '.day-tag[data-label="明天"]' in page
    assert 'tag.setAttribute("data-label", label)' in page


# ---------- 数据过期提醒 ----------

def test_page_records_update_time_for_stale_check():
    page = build_page(SAMPLE, NOW)
    # NOW = 2026-11-02 04:00 UTC
    assert '<p class="updated" data-updated="1793592000000">' in page
    assert '<span class="stale-note" hidden> · 课表可能不是最新</span>' in page
    assert ".updated.is-stale {" in page


# ---------- 翻页栏吸顶 ----------

def test_pager_bar_is_sticky():
    page = build_page(SAMPLE, NOW)
    assert ".pager-bar { position: sticky; top: 0;" in page
    assert ".pager-bar.is-stuck {" in page


def test_back_button_lives_inside_the_pager():
    page = build_page(SAMPLE, NOW)
    pager = page[page.index('<nav class="pager">'):page.index("</nav>")]
    assert '<button type="button" class="back" hidden>回到本周</button>' in pager
    assert page.count('class="back"') == 1
