"""命令行入口：python -m hunter <command>"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from hunter import repo
from hunter.config import PATHS, RUNTIME
from hunter.db import init_db
from hunter.models import Watch


def cmd_init(_args) -> int:
    init_db()
    PATHS.ensure()
    repo.account_ensure("default")
    print(f"已初始化。数据目录：{PATHS.data}")
    return 0


def cmd_serve(args) -> int:
    init_db()
    import uvicorn

    from hunter.web.app import app

    uvicorn.run(app, host=RUNTIME.host, port=args.port or RUNTIME.port, log_level="info")
    return 0


def cmd_login(args) -> int:
    from hunter.goofish.session import BrowserHub
    from hunter.login import interactive_login

    async def run():
        hub = BrowserHub()
        try:
            result = await interactive_login(hub, args.account, timeout=args.timeout)
        finally:
            await hub.close()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    return asyncio.run(run())


def cmd_import(args) -> int:
    from hunter.goofish.session import BrowserHub
    from hunter.login import check_login

    async def run():
        hub = BrowserHub()
        try:
            repo.account_ensure(args.account)
            count = await hub.import_state(args.account, args.path)
            state = await check_login(hub, args.account)
        finally:
            await hub.close()
        print(json.dumps({"imported": count, **state}, ensure_ascii=False))
        return 0

    return asyncio.run(run())


def cmd_add(args) -> int:
    init_db()
    watch = repo.watch_create(
        Watch(
            name=args.name,
            keyword=args.keyword,
            pages=args.pages,
            min_price=args.min_price,
            max_price=args.max_price,
            min_score=args.min_score,
            interval_sec=args.interval,
            personal_only=not args.any_condition,
            free_shipping=not args.any_condition,
            use_llm=not args.no_llm,
        )
    )
    print(f"已创建关注 #{watch.id}「{watch.name}」")
    return 0


def cmd_run(args) -> int:
    from hunter.pipeline import Pipeline

    async def run():
        pipeline = Pipeline()
        try:
            if args.watch:
                watches = [repo.watch_get(args.watch)]
            else:
                watches = repo.watch_list()
            for watch in watches:
                if not watch or watch.id is None:
                    continue
                if not args.all and not watch.enabled:
                    continue
                result = await pipeline.run_watch(watch.id, trigger="cli")
                print(json.dumps(result, ensure_ascii=False))
        finally:
            await pipeline.hub.close()
        return 0

    return asyncio.run(run())


def cmd_ls(_args) -> int:
    init_db()
    for watch in repo.watch_list():
        state = "开" if watch.enabled else "停"
        print(
            f"#{watch.id:<3} [{state}] {watch.name:<18} {watch.keyword:<20} "
            f"每 {watch.interval_sec}s · 门槛 {watch.min_score} · 商品 {repo.items_count(watch.id)}"
        )
    return 0


def cmd_doctor(_args) -> int:
    init_db()
    print(f"数据目录 : {PATHS.data}")
    print(f"数据库   : {PATHS.db} ({'存在' if PATHS.db.exists() else '不存在'})")
    print(f"浏览器   : {RUNTIME.browser_channel} · headless={RUNTIME.headless}")
    print(f"服务地址 : http://{RUNTIME.host}:{RUNTIME.port}")
    print(f"关注数   : {len(repo.watch_list())} · 商品数 {repo.items_count()}")
    accounts = repo.accounts_list()
    print(f"账号     : {', '.join(a['name'] + '/' + a['status'] for a in accounts) or '未配置'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hunter", description="闲鱼猎手：把监控做成决策")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="初始化数据库").set_defaults(func=cmd_init)

    serve = sub.add_parser("serve", help="启动 Web 服务")
    serve.add_argument("--port", type=int, default=None)
    serve.set_defaults(func=cmd_serve)

    login = sub.add_parser("login", help="打开窗口扫码登录")
    login.add_argument("--account", default="default")
    login.add_argument("--timeout", type=int, default=300)
    login.set_defaults(func=cmd_login)

    imp = sub.add_parser("import-state", help="导入浏览器登录态 JSON")
    imp.add_argument("--account", default="default")
    imp.add_argument("--path", required=True)
    imp.set_defaults(func=cmd_import)

    add = sub.add_parser("add", help="新建关注")
    add.add_argument("--name", required=True)
    add.add_argument("--keyword", required=True)
    add.add_argument("--pages", type=int, default=2)
    add.add_argument("--min-price", type=float, default=None)
    add.add_argument("--max-price", type=float, default=None)
    add.add_argument("--min-score", type=int, default=60)
    add.add_argument("--interval", type=int, default=300)
    add.add_argument("--any-condition", action="store_true", help="不加个人闲置/包邮筛选")
    add.add_argument("--no-llm", action="store_true")
    add.set_defaults(func=cmd_add)

    run = sub.add_parser("run", help="立即跑一次")
    run.add_argument("--watch", type=int, default=None)
    run.add_argument("--all", action="store_true", help="包括已停用的关注")
    run.set_defaults(func=cmd_run)

    sub.add_parser("ls", help="列出关注").set_defaults(func=cmd_ls)
    sub.add_parser("doctor", help="环境自检").set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    init_db()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
