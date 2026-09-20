# 项目约定

- 使用 uv 管理 Python 版本、虚拟环境和依赖，提交 uv.lock。
- 安装环境使用 `uv sync --locked`，执行 Python 和测试使用 `uv run`。
- 新增依赖使用 `uv add`；开发依赖使用 `uv add --dev`。
- Python 基线为 3.12，与目标服务器环境一致。
- 食谱库由笔记本整理并发布，服务器用户数据独立存储，不通过食谱同步覆盖。
