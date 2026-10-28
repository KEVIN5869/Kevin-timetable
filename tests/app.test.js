// static/app.js 的测试。运行：node --test
const test = require("node:test");
const assert = require("node:assert/strict");
const app = require("../static/app.js");

const utc = (iso) => Date.parse(iso);

test("dateKey 按北京时间算日期", () => {
  assert.equal(app.dateKey(utc("2026-11-01T15:59:59Z")), "2026-11-01"); // 北京 23:59:59
  assert.equal(app.dateKey(utc("2026-11-01T16:00:00Z")), "2026-11-02"); // 北京 00:00
});

test("addDays 能跨月", () => {
  assert.equal(app.addDays("2026-10-31", 1), "2026-11-01");
  assert.equal(app.addDays("2026-11-01", -1), "2026-10-31");
});

test("weekKey 返回北京时间那一周的周一", () => {
  assert.equal(app.weekKey(utc("2026-11-01T15:59:00Z")), "2026-10-26"); // 北京 周日 23:59
  assert.equal(app.weekKey(utc("2026-11-01T16:00:00Z")), "2026-11-02"); // 北京 周一 00:00
  assert.equal(app.weekKey(utc("2026-11-04T04:00:00Z")), "2026-11-02"); // 北京 周三
  assert.equal(app.weekKey(utc("2026-11-08T15:00:00Z")), "2026-11-02"); // 北京 周日 23:00
});

test("weekOffset 计算相差几周", () => {
  assert.equal(app.weekOffset("2026-11-02", "2026-11-02"), 0);
  assert.equal(app.weekOffset("2026-11-02", "2026-11-09"), 1);
  assert.equal(app.weekOffset("2026-11-02", "2026-10-26"), -1);
  assert.equal(app.weekOffset("2026-10-26", "2026-11-23"), 4);
});

test("weekLabel 文字", () => {
  assert.equal(app.weekLabel(0), "本周");
  assert.equal(app.weekLabel(1), "下周");
  assert.equal(app.weekLabel(-1), "上周");
  assert.equal(app.weekLabel(3), "3 周后");
  assert.equal(app.weekLabel(-2), "2 周前");
});

test("dayLabel 标注今天和明天（按北京时间）", () => {
  const now = utc("2026-11-01T16:30:00Z"); // 北京 11月2日 00:30
  assert.equal(app.dayLabel("2026-11-02", now), "今天");
  assert.equal(app.dayLabel("2026-11-03", now), "明天");
  assert.equal(app.dayLabel("2026-11-01", now), "");
  assert.equal(app.dayLabel("2026-11-04", now), "");
});

test("pickWeekIndex 默认选本周", () => {
  const weeks = ["2026-10-26", "2026-11-02", "2026-11-09"];
  assert.equal(app.pickWeekIndex(weeks, "2026-11-02"), 1);
});

test("pickWeekIndex 本周不在列表时选之后最近的一周", () => {
  const weeks = ["2026-10-26", "2026-11-09"];
  assert.equal(app.pickWeekIndex(weeks, "2026-11-02"), 1);
  assert.equal(app.pickWeekIndex(weeks, "2026-10-19"), 0);
});

test("pickWeekIndex 本周在所有周之后时选最后一周", () => {
  assert.equal(app.pickWeekIndex(["2026-10-26", "2026-11-02"], "2026-12-07"), 1);
});

test("pagerState 在本周", () => {
  const weeks = ["2026-10-26", "2026-11-02", "2026-11-09"];
  assert.deepEqual(app.pagerState(weeks, 1, "2026-11-02"), {
    label: "本周", canPrev: true, canNext: true, showBack: false,
  });
});

test("pagerState 翻到第一周和最后一周时不能再翻", () => {
  const weeks = ["2026-10-26", "2026-11-02", "2026-11-09"];
  assert.deepEqual(app.pagerState(weeks, 0, "2026-11-02"), {
    label: "上周", canPrev: false, canNext: true, showBack: true,
  });
  assert.deepEqual(app.pagerState(weeks, 2, "2026-11-02"), {
    label: "下周", canPrev: true, canNext: false, showBack: true,
  });
});

test("pagerState 本周不在列表里时不显示回到本周", () => {
  assert.equal(app.pagerState(["2026-10-26"], 0, "2026-11-02").showBack, false);
});

test("lessonState 判断已上完、正在上、还没开始（含边界）", () => {
  const start = utc("2026-11-02T11:45:00Z");
  const end = utc("2026-11-02T15:00:00Z");
  assert.equal(app.lessonState(start, end, start - 1), "future");
  assert.equal(app.lessonState(start, end, start), "now");        // 开始那一刻就算 NOW
  assert.equal(app.lessonState(start, end, end - 1), "now");
  assert.equal(app.lessonState(start, end, end), "past");         // 下课那一刻就不算了
});

test("followIndex 停在本周时，跨周后跟到新的本周", () => {
  const weeks = ["2026-10-26", "2026-11-02", "2026-11-09"];
  assert.equal(app.followIndex(weeks, 0, "2026-10-26", "2026-11-02"), 1);
});

test("followIndex 手动翻到别的周时，留在原地", () => {
  const weeks = ["2026-10-26", "2026-11-02", "2026-11-09"];
  assert.equal(app.followIndex(weeks, 2, "2026-10-26", "2026-11-02"), 2);
  assert.equal(app.followIndex(weeks, 2, "2026-10-26", "2026-10-26"), 2);
});

test("followIndex 没跨周时不变", () => {
  const weeks = ["2026-10-26", "2026-11-02"];
  assert.equal(app.followIndex(weeks, 0, "2026-10-26", "2026-10-26"), 0);
});

test("shouldReload 开着超过 30 分钟才重新加载", () => {
  const loaded = utc("2026-11-02T04:00:00Z");
  assert.equal(app.shouldReload(loaded, loaded + 30 * 60 * 1000), false);
  assert.equal(app.shouldReload(loaded, loaded + 30 * 60 * 1000 + 1), true);
});
