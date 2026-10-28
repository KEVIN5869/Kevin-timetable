# Kevin 的课表

把 TimeEdit 课表（ics 订阅链接）转换成北京时间的手机网页，托管在 GitHub Pages，每 20 分钟自动更新。

## 文件说明

| 文件 | 作用 |
|---|---|
| `timetable.py` | 核心逻辑：解析 ics、换算北京时间、分组、生成网页 |
| `build.py` | 拉取 ics，生成 `_site/index.html` |
| `tests/` | 测试（使用假的样例课表 `tests/fixtures/sample.ics`） |
| `.github/workflows/deploy.yml` | 自动更新：每 20 分钟测试、生成并发布 |
| `.env` | 本地的 ics 链接（`ICS_URL=...`），不提交 |

## 本地使用

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest          # 跑测试
.venv/bin/python build.py # 生成网页到 _site/index.html
```

## 线上配置

- ics 链接保存在 GitHub 仓库的 Settings → Secrets and variables → Actions → `ICS_URL`
- Settings → Pages → Source 选 **GitHub Actions**
