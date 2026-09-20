# 部署结构

GitHub Actions 执行 uv 锁定安装、测试、前端构建，生成 `cookflow-release` artifact。前端基础路径为 `/cookflow/`。本机构建根路径仍使用 `npm --prefix web run build`。

服务器目录：

- `/opt/cookflow/releases/<commit>/`：发布产物与 Python 虚拟环境。
- `/opt/cookflow/current`：当前发布目录软链接。
- `/var/lib/cookflow/catalog.sqlite`：笔记本发布的食谱快照，应用只读。
- `/var/lib/cookflow/user.sqlite`：应用写入的用户配置与进度。

安装流程：解压产物，在发布目录执行 `uv sync --locked --no-dev --python /usr/bin/python3`；把笔记本 `cookflow publish` 生成的快照上传后先运行 `cookflow verify`，再安装食谱库；安装 `cookflow.service`，在已有 HTTPS server 中 include `nginx-cookflow.conf`，通过 `nginx -t` 后 reload。

应用使用独立的 cookflow 系统用户，只监听回环地址 8100，由 Nginx 提供 HTTPS。网站无需注册、登录或访问密码，当前版本使用共享的厨房记录。

更新代码时使用新的发布目录，更换 current 链接后重启 cookflow。更新食谱时保留旧文件备份，原子替换 catalog.sqlite；不要覆盖 user.sqlite。回滚代码只需恢复 current 指向上一发布目录。

自动构建已配置；生产发布目前由管理员通过 SSH 执行。
