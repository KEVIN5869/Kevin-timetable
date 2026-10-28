// 课表网页的脚本：选出"本周"、翻页、标注"今天/明天"。
// 时间一律按北京时间（UTC+8，中国没有夏令时）计算，不受手机时区设置影响。
// 上半部分是纯函数（有测试：tests/app.test.js），下半部分把结果显示到网页上。
(function () {
  "use strict";

  var DAY_MS = 24 * 60 * 60 * 1000;
  var BEIJING_OFFSET_MS = 8 * 60 * 60 * 1000;

  function pad(n) {
    return (n < 10 ? "0" : "") + n;
  }

  function formatKey(date) {
    return date.getUTCFullYear() + "-" + pad(date.getUTCMonth() + 1) + "-" + pad(date.getUTCDate());
  }

  function keyToUtcMs(key) {
    var parts = key.split("-");
    return Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  }

  // 时间戳 → 北京日期 "YYYY-MM-DD"
  function dateKey(ms) {
    return formatKey(new Date(ms + BEIJING_OFFSET_MS));
  }

  function addDays(key, days) {
    return formatKey(new Date(keyToUtcMs(key) + days * DAY_MS));
  }

  // 时间戳 → 所在周的周一 "YYYY-MM-DD"
  function weekKey(ms) {
    var key = dateKey(ms);
    var weekday = new Date(keyToUtcMs(key)).getUTCDay(); // 0 = 周日
    return addDays(key, -((weekday + 6) % 7));
  }

  // 两个周一之间差几周
  function weekOffset(fromKey, toKey) {
    return Math.round((keyToUtcMs(toKey) - keyToUtcMs(fromKey)) / (7 * DAY_MS));
  }

  function weekLabel(offset) {
    if (offset === 0) return "本周";
    if (offset === 1) return "下周";
    if (offset === -1) return "上周";
    if (offset > 1) return offset + " 周后";
    return -offset + " 周前";
  }

  function dayLabel(dayKey, nowMs) {
    var today = dateKey(nowMs);
    if (dayKey === today) return "今天";
    if (dayKey === addDays(today, 1)) return "明天";
    return "";
  }

  // 默认显示哪一周：本周；本周不在列表里时，显示之后最近的一周，再不行显示最后一周
  function pickWeekIndex(weekKeys, currentKey) {
    for (var i = 0; i < weekKeys.length; i++) {
      if (weekKeys[i] >= currentKey) return i;
    }
    return weekKeys.length - 1;
  }

  // 翻页栏应该显示什么
  function pagerState(weekKeys, index, currentKey) {
    return {
      label: weekLabel(weekOffset(currentKey, weekKeys[index])),
      canPrev: index > 0,
      canNext: index < weekKeys.length - 1,
      showBack: weekKeys[index] !== currentKey && weekKeys.indexOf(currentKey) !== -1,
    };
  }

  var api = {
    dateKey: dateKey,
    addDays: addDays,
    weekKey: weekKey,
    weekOffset: weekOffset,
    weekLabel: weekLabel,
    dayLabel: dayLabel,
    pickWeekIndex: pickWeekIndex,
    pagerState: pagerState,
  };

  if (typeof module === "object" && module.exports) {
    module.exports = api; // 在 Node 里跑测试
    return;
  }

  // ---------- 下面只在浏览器里运行 ----------

  var doc = document;
  doc.documentElement.className += " js";
  var sections = Array.prototype.slice.call(doc.querySelectorAll(".week"));
  if (!sections.length) return;
  var weekKeys = sections.map(function (s) { return s.getAttribute("data-week"); });
  var pager = doc.querySelector(".pager");
  var back = doc.querySelector(".back");
  var index = pickWeekIndex(weekKeys, weekKey(Date.now()));

  function render() {
    var now = Date.now();
    var currentKey = weekKey(now);
    var state = pagerState(weekKeys, index, currentKey);
    sections.forEach(function (section, i) {
      section.hidden = i !== index;
    });
    pager.querySelector(".week-label").textContent = state.label;
    pager.querySelector(".week-range").textContent = sections[index].getAttribute("data-range");
    pager.querySelector(".prev").disabled = !state.canPrev;
    pager.querySelector(".next").disabled = !state.canNext;
    back.hidden = !state.showBack;
    Array.prototype.forEach.call(doc.querySelectorAll(".day"), function (day) {
      var label = dayLabel(day.getAttribute("data-date"), now);
      var tag = day.querySelector(".day-tag");
      tag.textContent = label;
      tag.hidden = !label;
    });
  }

  pager.querySelector(".prev").addEventListener("click", function () {
    if (index > 0) { index--; render(); }
  });
  pager.querySelector(".next").addEventListener("click", function () {
    if (index < weekKeys.length - 1) { index++; render(); }
  });
  back.addEventListener("click", function () {
    index = pickWeekIndex(weekKeys, weekKey(Date.now()));
    render();
  });

  pager.hidden = false;
  render();
})();
