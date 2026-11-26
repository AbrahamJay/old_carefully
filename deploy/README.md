# deploy/ · 部署入口

本目录是服务器部署的唯一入口。**完整部署步骤、变量说明、排障表统一在
[`../docs/部署文档.md`](../docs/部署文档.md)**，这里只做目录索引，不再重复内容（避免两份文档漂移）。

## 文件清单

| 文件 | 作用 | 文档位置 |
| --- | --- | --- |
| `docker-compose.yml` | 编排 `api` / `admin` / `h5` / `nginx` 四个服务；PG、MinIO 走外部 | §1、§3 |
| `.env.example` | 部署变量模板，复制成 `.env` 后填 | §4 |
| `Dockerfile.api` | `python:3.12-slim` + `pip install -r requirements.txt` | §2、§5.5 |
| `requirements.txt` | 由 `apps/api/uv.lock` 导出的锁定运行依赖 | §8（依赖变更时重新导出） |
| `Dockerfile.admin` / `Dockerfile.h5` | 多阶段构建：`node:22` 构建 → `nginx:alpine` 托管 | §2、§5.5 |
| `nginx/default.conf` | 入口网关：`/api/` → api、`/h5/` → h5、`/` → admin | §3、§12 |
| `nginx/admin.conf` / `nginx/h5.conf` | 静态站配置（SPA 兜底 + 缓存头） | §3 |

## 最短路径（已部署过、只是更新代码）

```bash
cd /opt/socialoldcare && git pull
cd deploy
docker compose build <api|admin|h5>     # 改了什么建什么；只改 nginx 配置不用 build
docker compose up -d
```

首次部署、变量填写、验收清单、`apply_sql.py` 为什么不能跑、常见故障 → 见
[`../docs/部署文档.md`](../docs/部署文档.md)。
