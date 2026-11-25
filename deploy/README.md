# 服务器部署（deploy/ 是唯一入口）

目标机：`120.53.13.162`（Ubuntu + Docker 已就绪）

服务器上**已有**、本项目**不创建也不管理**的设施：

| 设施 | 现状 | 本项目怎么用 |
| --- | --- | --- |
| PostgreSQL | `pgvector/pgvector:pg16`，容器名 `pg`，宿主 `127.0.0.1:5432` | 接入共享网络，用别名 `postgres` 访问，**不重建、不动数据** |
| MinIO | 已监听 `9000` | 容器就接入网络别名 `minio`；宿主二进制就用 `host.docker.internal:9000` |
| MongoDB | `mongo:7.0`，`27017` | 与本项目无关，**不要动** |

本次部署产出 4 个容器：`socialoldcare-api`、`socialoldcare-admin`、`socialoldcare-h5`、`socialoldcare-nginx`（对外只暴露 80）。

---

## 0. 目录清单

```
deploy/
├── docker-compose.yml     # 编排：api / admin / h5 / nginx（PG、MinIO 走外部）
├── .env.example           # 环境变量模板 → 复制成 .env 再填
├── Dockerfile.api         # python:3.12-slim + pip 装 requirements.txt
├── Dockerfile.admin       # node:22 构建 Vue → nginx:alpine 托管
├── Dockerfile.h5          # 同上
├── requirements.txt       # 后端运行依赖（由 apps/api/uv.lock 导出，已锁版本）
└── nginx/
    ├── default.conf       # 入口网关：/api/ → api:8000、/h5/ → h5:80、/ → admin:80
    ├── admin.conf         # admin 容器内静态站（SPA 兜底 + 长缓存）
    └── h5.conf            # h5 容器内静态站
```

三个 Dockerfile 的构建上下文都是**仓库根目录**（`context: ..`），因为要读 `../apps/**` 源码。所以必须把整个仓库放到服务器，不能只拷 `deploy/` 目录。

> 仓库根目录原有的 `docker-compose.yml`、`.env.example` 已全部收敛到 `deploy/`，避免两套配置漂移；`apps/*/Dockerfile`、`apps/*/nginx.conf` 保留给本地/CI 使用，服务器一律走 `deploy/`。

---

## 1. 上传代码

```bash
sudo mkdir -p /opt/socialoldcare
sudo chown -R "$USER":"$USER" /opt/socialoldcare

git clone https://github.com/AbrahamJay/old_carefully.git /opt/socialoldcare
cd /opt/socialoldcare/deploy
```

仓库没推上来时（本地 rsync 直传，注意 `--exclude` 与根 `.dockerignore` 保持一致）：

```bash
rsync -avz --delete \
  --exclude '.git' --exclude '.idea' --exclude 'node_modules' --exclude 'dist' \
  --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.ruff_cache' \
  --exclude '.env' \
  ./ root@120.53.13.162:/opt/socialoldcare/
```

---

## 2. 建共享网络，把已有 PG / MinIO 接进来

服务之间靠容器名互访，所以所有容器必须在同一个 Docker 网络里。

```bash
# 1) 建网络（已存在会报错，忽略即可）
docker network create socialoldcare-net

# 2) 把现有 PG 接进去，并起别名 postgres（.env 里 POSTGRES_HOST=postgres 就是它）
docker network connect --alias postgres socialoldcare-net pg
```

`docker network connect` 对同一个容器重复执行会报 `already exists`，忽略；网络连接会随容器重启保留，但**如果 `pg` 容器被删除重建，别名会丢失，需要重连一次**。

MinIO 分两种情况，先看它是不是容器：

```bash
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' | grep ':9000'
```

- **是容器**（有输出）：接入同一网络并起别名 `minio`

  ```bash
  docker network connect --alias minio socialoldcare-net <上面查到的容器名>
  ```

  然后 `.env` 里保持 `MINIO_ENDPOINT=minio:9000`。

- **是宿主机二进制**（无输出）：不用接入网络，`.env` 里改成

  ```ini
  MINIO_ENDPOINT=host.docker.internal:9000
  ```

  （compose 已给 api 加了 `extra_hosts: host.docker.internal:host-gateway`；且要求 MinIO 监听 `0.0.0.0`，只绑 `127.0.0.1` 时容器访问不到。）

连通性自检（可选，busybox 很小）：

```bash
docker run --rm --network socialoldcare-net busybox nslookup postgres
docker run --rm --network socialoldcare-net busybox nslookup minio
```

---

## 3. 填 .env

```bash
cd /opt/socialoldcare/deploy
cp .env.example .env
chmod 600 .env
openssl rand -hex 32        # 生成 JWT_SECRET
vim .env
```

必填 4 项：

| 变量 | 填什么 |
| --- | --- |
| `POSTGRES_PASSWORD` | 服务器上**现有 PG 的真实密码**（旧 `apps/api/.env` 里那套），填错连不上库 |
| `JWT_SECRET` | `openssl rand -hex 32` 的输出（64 位 hex）；占位符只有 32 位，`APP_ENV=prod` 下会启动失败 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | 现有 MinIO 的凭据 |
| `MINIO_PUBLIC_BASE_URL` | 浏览器可达前缀，默认 `http://120.53.13.162:9000/socialoldcare-media` |

`APP_ENV=prod` 会强制校验 `ALLOW_DEMO_LOGIN=false`、`AUTO_SEED=false`，改错会直接启动失败——这是刻意的保护。

---

## 4. 构建并启动

```bash
cd /opt/socialoldcare/deploy

# 国内网络慢时，Dockerfile 已默认用清华 PyPI 源 + npmmirror npm 源
docker compose build            # 首次约 3~6 分钟
docker compose up -d
docker compose ps               # api 应变为 healthy
docker compose logs -f api      # Ctrl+C 退出
docker compose exec nginx nginx -t   # 配置语法自检
```

端口冲突排查（80 必须空闲）：

```bash
ss -ltnp | grep -E ':80 |:8000 '
```

---

## 5. 初始化数据

`AUTO_MIGRATE=true` 时 api 启动已自动执行 `alembic upgrade head`，先确认：

```bash
docker compose exec api alembic current
```

再灌基础数据（站点 / 账号 / 老人档案 / 服务项目，幂等可重复跑；**不含订单等业务数据**）：

```bash
docker compose exec api python scripts/apply_sql.py      # sql/*.sql
docker compose exec api python scripts/init_minio.py     # 建桶 + 匿名只读（图片可直连）
docker compose exec api python scripts/create_admin.py --phone 13900000000 --name 管理员
```

`create_admin.py` 的密码是交互式输入（不回显），按提示输入两次即可。

---

## 6. 验收

```bash
curl -s  http://127.0.0.1/healthz; echo                 # {"status":"ok",...}
curl -s -o /dev/null -w 'admin %{http_code}\n' http://127.0.0.1/
curl -s -o /dev/null -w 'h5    %{http_code}\n' http://127.0.0.1/h5/
curl -s  http://127.0.0.1/api/v1/__ping; echo           # {"detail":"Not Found"} = 已到 FastAPI
```

最后一条如果返回 HTML，说明 `/api/` 落到了 admin 静态站，检查 `docker compose exec nginx nginx -t` 与 `nginx/default.conf`。

浏览器验收：

1. `http://120.53.13.162/` → 管理后台登录页，用第 5 步的账号登录；
2. `http://120.53.13.162/h5/` → H5 首页（`/h5/orders/xx` 直接刷新不能 404）；
3. 后台上传一张图片 → 返回的 `MINIO_PUBLIC_BASE_URL` 直链能直接打开（打不开说明第 3 步的 IP/桶名写错，或 `init_minio.py` 没跑）；
4. 云服务器安全组放行 `80`（`9000`、`22` 保持现状）。

---

## 7. 更新与运维

```bash
cd /opt/socialoldcare
git pull
cd deploy
docker compose build && docker compose up -d
docker compose exec api alembic current     # 确认迁移已生效
```

- 只改了 nginx 配置：`docker compose restart nginx`（配置是只读挂载，改完即生效，restart 只为保险）
- 备份数据库（沿用现有 `pg` 容器，无损）：

  ```bash
  docker exec pg pg_dump -U socialoldcare socialoldcare | gzip > /opt/backup-$(date +%F).sql.gz
  ```

- 看日志：`docker compose logs -f --tail=200 api`

---

## 8. 常见问题

| 现象 | 原因 / 处理 |
| --- | --- |
| `network socialoldcare-net not found` | 第 2 步没建网络，先 `docker network create socialoldcare-net` |
| `network ... has incorrect label` | 网络不是 compose 建的；本项目用 `external: true`，若仍报错说明本地还留着旧的 compose 网络，`docker network rm` 后重建 |
| api 反复重启 + 日志 `JWT_SECRET` | 占位符没换成 `openssl rand -hex 32` |
| api 日志 `could not translate host name "postgres"` | `pg` 容器没接入网络：重跑 `docker network connect --alias postgres socialoldcare-net pg` |
| api 连 MinIO 超时 | MinIO 是容器却没接入网络，或 .env 里 `MINIO_ENDPOINT` 填成了 `127.0.0.1:9000`（容器内 127.0.0.1 是它自己） |
| 图片 302 到 `minio:9000` 打不开 | `MINIO_PUBLIC_BASE_URL` 必须是浏览器可达地址（服务器 IP:9000），不能写容器名 |
| 前端页面 200 但接口全 404 | 入口 nginx 的 `/api/` 没生效，`nginx -t` + 看 `location /api/` 的 `proxy_pass` 是否无 URI 结尾 |
| `/h5/` 白屏、资源 404 | h5 构建 base 必须是 `/h5/`（`Dockerfile.h5` 已用生产模式构建），且网关 `proxy_pass http://h5:80/` 末尾要带 `/` |
| 构建时 pip/npm 卡住 | 换源：`docker compose build --build-arg PIP_INDEX_URL=https://pypi.org/simple --build-arg NPM_REGISTRY=https://registry.npmjs.org` |
