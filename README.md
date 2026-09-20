# CookFlow

在笔记本抓取、整理和发布食谱，在轻量服务器上提供选菜和做饭调度。

初版已打通 **10 道真实来源菜谱 → 本地版本库 → FastAPI → React 界面 → 调度确认 → 时间线和进度保存**。

公开仓库：<https://github.com/Georicl/CookFlow>

## 启动

Python 3.12 由 uv 管理；前端使用 Node.js 和 npm。

```bash
uv sync --locked
uv run cookflow seed
npm --prefix web ci
npm --prefix web run build
uv run cookflow serve
```

打开 http://127.0.0.1:8000 。接口文档在 http://127.0.0.1:8000/docs 。

开发前端时，保持 API 运行，另开终端运行 `npm --prefix web run dev`，Vite 将 `/api` 代理到 8000 端口。

## 已实现

- 中文食谱卡片、名称/食材搜索、分类筛选、详情和来源链接。
- 菜单选择（最多 6 道）与人员、灶头、炒锅、汤锅、砧板和烤箱配置。
- 调度编辑器：修改/增删步骤、输入耗时、选择主动/被动和厨具、确认份数。
- 基于资源容量的可行时间线；保存菜单快照、勾选步骤、恢复历史进度。
- API 只读食谱数据库；确认信息和计划写入独立的用户数据库。
- 本地官方 API 抓取、原文缓存、规范化 JSON、版本去重、发布快照与校验。

## 首批食谱

通过 TheMealDB 官方 API 获取，展示名为中文译名，食材和做法保留英文原文：

番茄炒蛋、麻婆豆腐、宫保鸡丁、糖醋猪肉、蛋花汤、酸辣汤、鸡肉粥、鸡肉炒饭、芝麻黄瓜沙拉、荷兰豆炒虾仁。

早先的原创番茄炒蛋开发模板仍保留，因此这台笔记本的现有库共 11 条记录。全新环境执行 `seed` 会得到 10 条。

原始响应在 `data/raw/themealdb/`；整理后的文档在 `recipes/imported/`。`seed` 默认使用本地缓存，`seed --refresh` 重新请求官方 API。内容相同不新建版本；抓取时间在原文未变化时保持不变。

每条外部记录保留来源 URL、API URL、抓取时间、原文 SHA-256、署名与条款链接。TheMealDB 内容使用遵循其 [Terms of Use](https://www.themealdb.com/terms_of_use.php)，不是将整个数据集重新许可为项目代码许可证。首轮曾尝试的 53371 因 API 只有说明而无完整做法被排除，保留在本地 `data/rejected/`。

## 使用流程

1. 选择想做的菜。
2. 打开「调度信息」，根据实际做法填写每步分钟数和设备，确认份数并保存。
3. 在「厨房配置」设置可用人员和厨具数量。
4. 点击「生成做饭时间线」，按步骤勾选进度。
5. 在「最近的安排」恢复已保存的计划。

来源不提供逐步耗时和份数，因此新导入食谱为 `draft`，份数初值 2 明确标为待确认。确认后形成用户自己的调度配置，不改写来源库；字段记录为用户估计，而非实测。原始内容更新后，旧调度配置会标为过期，需重新确认。

## 数据与同步

```text
笔记本：官方 API → 原始响应 → 规范化食谱 → catalog.sqlite → 发布目录
服务器：验证发布目录 → 切换食谱库 → API 只读访问
用户操作：调度配置、计划快照、完成进度 → user.sqlite
```

```bash
uv run cookflow list
uv run cookflow import recipes/zh-CN/tomato-egg.json
uv run cookflow publish releases/my-release
uv run cookflow verify releases/my-release
```

发布目录必须不存在，包含一致性备份 `catalog.sqlite` 和 `manifest.json`。校验覆盖文件摘要、SQLite 完整性、内容哈希、版本指针和食谱格式。摘要检测传输损坏，不提供身份认证。发布不包含用户数据。

服务可通过 `COOKFLOW_USERS` 指定用户库；食谱库使用 `uv run cookflow --db <path> serve`。本地服务默认只监听 `127.0.0.1:8000`。服务器使用独立 systemd 服务、Nginx 子路径，详见 [部署说明](deploy/README.md)。网站无需注册、登录或访问密码；当前版本使用共享的厨房记录。

## 调度模型

- 每步记录耗时、依赖、人工/设备占用，`passive` 可释放人员，但仍保留指定设备。
- 验证无环依赖与资源容量。主动步骤必须占用人员。
- 初版按拓扑顺序串行安排一道菜内部的步骤，再寻找不同菜之间不冲突的开始时间；不是全局最优求解器。
- `resource_holds` 保留跨步骤的锅具占用，与同一步的同类资源需求合并而非重复计数。
- 界面为每道菜自动保留一口炒锅/汤锅直到最后使用；复杂的多锅切换可后续扩展。
- 菜单保存完整版本快照，来源库更新不会改变正在执行的计划。
- 目前勾选只记录完成状态，不按实际延误重新排程；份数不会自动线性缩放耗时或食材。

## 目录

```text
cookflow/
  catalog.py       食谱校验、版本与发布
  importer.py      TheMealDB 抓取与规范化
  api.py           食谱、调度配置、计划和进度接口
  scheduler.py     资源约束时间线
  cli.py           本地命令
web/src/           React + TypeScript 界面
recipes/imported/  可追溯的规范化来源食谱
recipes/zh-CN/     本地开发模板
tests/             数据库、来源、API 与调度测试
```

## 验证

```bash
uv run pytest -q
npm --prefix web run build
```

测试覆盖重复导入不回退版本、环依赖拒绝、审核要求、跨步骤设备占用、发布损坏检测、API 全流程、用户库与来源库隔离、过期确认拒绝、资源不足、被动步骤并行、原文哈希与规范化可复现。
