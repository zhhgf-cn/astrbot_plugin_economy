import asyncio
from typing import Optional

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger
from astrbot.core.agent.tool import ToolSet

from .database import EconomyDB
from .stock import StockSystem
from .tools import BalanceTool, SignTool, ShopTool, StockTool, RankingTool


class EconomyPlugin(Star):
    """经济系统插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # 初始化数据库
        self.db = EconomyDB("astrbot_plugin_economy")

        # 初始化股票系统
        self.stock_system = StockSystem(
            self.db,
            max_change=config.get("max_price_change", 10) / 100
        )

        # 初始化 AI 工具
        self.balance_tool = BalanceTool()
        self.balance_tool.db = self.db
        self.balance_tool.admin_ids = config.get("admin_ids", [])

        self.sign_tool = SignTool()
        self.sign_tool.db = self.db
        self.sign_tool.sign_reward = config.get("sign_reward", 10)
        self.sign_tool.sign_bonus = config.get("sign_bonus", 5)

        self.shop_tool = ShopTool()
        self.shop_tool.db = self.db
        self.shop_tool.admin_ids = config.get("admin_ids", [])

        self.stock_tool = StockTool()
        self.stock_tool.db = self.db
        self.stock_tool.stock_system = self.stock_system
        self.stock_tool.admin_ids = config.get("admin_ids", [])

        self.ranking_tool = RankingTool()
        self.ranking_tool.db = self.db
        self.ranking_tool.stock_system = self.stock_system

        # 注册 AI 工具
        self.context.add_llm_tools(
            self.balance_tool,
            self.sign_tool,
            self.shop_tool,
            self.stock_tool,
            self.ranking_tool
        )

        # 启动股价自动更新任务
        if config.get("enable_stock_system", True):
            asyncio.create_task(self._stock_updater())

        logger.info("经济系统插件已加载")

    async def _stock_updater(self):
        """后台任务：自动更新股价"""
        interval = self.config.get("stock_update_interval", 30) * 60
        while True:
            try:
                await asyncio.sleep(interval)
                results = self.stock_system.update_all_prices()
                updated = [r for r in results if r.get("success")]
                if updated:
                    logger.info(f"股价已更新: {len(updated)}只股票")
            except Exception as e:
                logger.error(f"股价更新失败: {e}")

    # ==================== 打卡签到 ====================

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_checkin(self, event: AstrMessageEvent):
        """处理打卡命令，精确匹配'打卡'两个字"""
        msg = event.message_str.strip()
        if msg == "打卡":
            user_id = event.get_sender_id()
            result = self.db.do_sign(
                user_id,
                self.config.get("sign_reward", 10),
                self.config.get("sign_bonus", 5)
            )
            yield event.plain_result(result["message"])

    # ==================== 金币命令 ====================

    @filter.command("余额", aliases=["金币"])
    async def check_coins(self, event: AstrMessageEvent):
        """查看金币余额"""
        user_id = event.get_sender_id()
        coins = self.db.get_coins(user_id)
        yield event.plain_result(f"你当前有 {coins} 金币")

    @filter.command("转账")
    async def transfer_coins(self, event: AstrMessageEvent, target: str = "", amount: str = ""):
        """转账给其他人"""
        if not target or not amount:
            yield event.plain_result(
                "转账命令用法: /转账 @用户 金额\n"
                "例如: /转账 @张三 100"
            )
            return
        
        try:
            amount_int = int(amount)
        except ValueError:
            yield event.plain_result("金额必须是数字")
            return
        
        user_id = event.get_sender_id()
        # 解析目标用户ID（移除@符号）
        target_id = target.lstrip("@")
        if user_id == target_id:
            yield event.plain_result("不能给自己转账")
            return
        if amount_int <= 0:
            yield event.plain_result("转账金额必须大于0")
            return
        if self.db.remove_coins(user_id, amount_int):
            self.db.add_coins(target_id, amount_int)
            yield event.plain_result(
                f"转账成功! 向 {target_id} 转账 {amount_int} 金币，"
                f"当前余额: {self.db.get_coins(user_id)}"
            )
        else:
            yield event.plain_result(f"金币不足，当前余额: {self.db.get_coins(user_id)}")

    # ==================== 管理员命令 ====================

    @filter.command("加币")
    async def add_coins(self, event: AstrMessageEvent, target: str = "", amount: str = ""):
        """给用户增加金币（管理员）"""
        if not target or not amount:
            yield event.plain_result(
                "加币命令用法: /加币 @用户 金额\n"
                "例如: /加币 @张三 100"
            )
            return
        
        try:
            amount_int = int(amount)
        except ValueError:
            yield event.plain_result("金额必须是数字")
            return
        
        user_id = event.get_sender_id()
        if user_id not in self.config.get("admin_ids", []):
            yield event.plain_result("只有管理员才能使用此命令")
            return
        
        target_id = target.lstrip("@")
        new_balance = self.db.add_coins(target_id, amount_int)
        yield event.plain_result(
            f"操作成功! 给 {target_id} 增加 {amount_int} 金币\n"
            f"该用户当前余额: {new_balance}"
        )

    @filter.command("减币")
    async def remove_coins(self, event: AstrMessageEvent, target: str = "", amount: str = ""):
        """扣除用户金币（管理员）"""
        if not target or not amount:
            yield event.plain_result(
                "减币命令用法: /减币 @用户 金额\n"
                "例如: /减币 @张三 50"
            )
            return
        
        try:
            amount_int = int(amount)
        except ValueError:
            yield event.plain_result("金额必须是数字")
            return
        
        user_id = event.get_sender_id()
        if user_id not in self.config.get("admin_ids", []):
            yield event.plain_result("只有管理员才能使用此命令")
            return
        
        target_id = target.lstrip("@")
        current = self.db.get_coins(target_id)
        if current < amount_int:
            yield event.plain_result(
                f"该用户当前余额: {current}，不足以扣除 {amount_int}"
            )
            return
        
        self.db.remove_coins(target_id, amount_int)
        new_balance = self.db.get_coins(target_id)
        yield event.plain_result(
            f"操作成功! 扣除 {target_id} {amount_int} 金币\n"
            f"该用户当前余额: {new_balance}"
        )

    @filter.command("设置币")
    async def set_coins(self, event: AstrMessageEvent, target: str = "", amount: str = ""):
        """设置用户金币数量（管理员）"""
        if not target or not amount:
            yield event.plain_result(
                "设置币命令用法: /设置币 @用户 金额\n"
                "例如: /设置币 @张三 1000"
            )
            return
        
        try:
            amount_int = int(amount)
        except ValueError:
            yield event.plain_result("金额必须是数字")
            return
        
        user_id = event.get_sender_id()
        if user_id not in self.config.get("admin_ids", []):
            yield event.plain_result("只有管理员才能使用此命令")
            return
        
        target_id = target.lstrip("@")
        self.db.set_coins(target_id, amount_int)
        yield event.plain_result(
            f"操作成功! 设置 {target_id} 的金币为 {amount_int}"
        )

    # ==================== 商店命令 ====================

    @filter.command("商店")
    async def shop_list(self, event: AstrMessageEvent):
        """查看商店商品"""
        items = self.db.get_shop_items()
        if not items:
            yield event.plain_result("商店暂时没有商品")
            return

        lines = ["=== 商店商品列表 ==="]
        for item in items:
            lines.append(f"[ID:{item['item_id']}] {item['name']}")
            lines.append(f"  价格: {item['price']}金币 | 库存: {item['stock']}")
            if item['description']:
                lines.append(f"  描述: {item['description']}")
            lines.append("")
        yield event.plain_result("\n".join(lines))

    @filter.command("购买")
    async def buy_item(self, event: AstrMessageEvent, item_id: str = ""):
        """购买商品"""
        if not item_id:
            yield event.plain_result(
                "购买命令用法: /购买 商品ID\n"
                "先使用 /商店 查看商品列表"
            )
            return
        
        try:
            item_id_int = int(item_id)
        except ValueError:
            yield event.plain_result("商品ID必须是数字")
            return
        
        user_id = event.get_sender_id()
        result = self.db.buy_shop_item(item_id_int, user_id)
        yield event.plain_result(result["message"])

    @filter.command("上架")
    async def add_item(self, event: AstrMessageEvent, name: str = "", price: str = "", description: str = ""):
        """上架商品（管理员）"""
        if not name or not price:
            yield event.plain_result(
                "上架命令用法: /上架 名称 价格 描述\n"
                "例如: /上架 草莓蛋糕 50 好吃的草莓蛋糕"
            )
            return
        
        try:
            price_int = int(price)
        except ValueError:
            yield event.plain_result("价格必须是数字")
            return
        
        user_id = event.get_sender_id()
        if user_id not in self.config.get("admin_ids", []):
            yield event.plain_result("只有管理员才能上架商品")
            return

        item_id = self.db.add_shop_item(
            name=name,
            price=price_int,
            description=description,
            added_by=user_id
        )
        yield event.plain_result(
            f"上架成功! 商品ID: {item_id}\n"
            f"名称: {name}\n"
            f"价格: {price_int}金币\n"
            f"描述: {description}"
        )

    @filter.command("下架")
    async def remove_item(self, event: AstrMessageEvent, item_id: str = ""):
        """下架商品（管理员）"""
        if not item_id:
            yield event.plain_result(
                "下架命令用法: /下架 商品ID\n"
                "先使用 /商店 查看商品列表"
            )
            return
        
        try:
            item_id_int = int(item_id)
        except ValueError:
            yield event.plain_result("商品ID必须是数字")
            return
        
        user_id = event.get_sender_id()
        if user_id not in self.config.get("admin_ids", []):
            yield event.plain_result("只有管理员才能下架商品")
            return

        item = self.db.get_shop_item(item_id_int)
        if not item:
            yield event.plain_result("商品不存在")
            return

        self.db.remove_shop_item(item_id_int)
        yield event.plain_result(f"已下架商品: {item['name']}")

    # ==================== 股票命令 ====================

    @filter.command("股票")
    async def stock_list(self, event: AstrMessageEvent, stock_id: str = None):
        """查看股票列表或详情"""
        if stock_id:
            info = self.stock_system.get_stock_info(stock_id)
            if not info:
                yield event.plain_result(f"股票 {stock_id} 不存在")
                return

            lines = [
                f"=== {info['name']} ({info['stock_id']}) ===",
                f"当前价格: {info['price']}金币",
                f"基准价格: {info['base_price']}金币",
                f"涨跌幅: {info['change']}% {info['trend_emoji']}",
                f"趋势: {info['trend']}"
            ]
            yield event.plain_result("\n".join(lines))
        else:
            stocks = self.stock_system.get_all_stocks_info()
            if not stocks:
                yield event.plain_result("暂无股票")
                return

            lines = ["=== 股票列表 ==="]
            for s in stocks:
                lines.append(f"[{s['stock_id']}] {s['name']}")
                lines.append(f"  价格: {s['price']}金币 | 涨跌: {s['change']}% {s['trend_emoji']}")
            yield event.plain_result("\n".join(lines))

    @filter.command("买入")
    async def buy_stock(self, event: AstrMessageEvent, stock_id: str = "", shares: str = ""):
        """买入股票"""
        if not stock_id or not shares:
            yield event.plain_result(
                "买入命令用法: /买入 股票代码 数量\n"
                "例如: /买入 BTC 10\n"
                "先使用 /股票 查看股票列表"
            )
            return
        
        try:
            shares_int = int(shares)
        except ValueError:
            yield event.plain_result("数量必须是数字")
            return
        
        user_id = event.get_sender_id()
        stock = self.db.get_stock(stock_id)
        if not stock:
            yield event.plain_result(f"股票 {stock_id} 不存在")
            return

        result = self.db.buy_stock(user_id, stock_id, shares_int, stock["price"])
        yield event.plain_result(result["message"])

    @filter.command("卖出")
    async def sell_stock(self, event: AstrMessageEvent, stock_id: str = "", shares: str = ""):
        """卖出股票"""
        if not stock_id or not shares:
            yield event.plain_result(
                "卖出命令用法: /卖出 股票代码 数量\n"
                "例如: /卖出 BTC 10\n"
                "先使用 /持仓 查看持仓"
            )
            return
        
        try:
            shares_int = int(shares)
        except ValueError:
            yield event.plain_result("数量必须是数字")
            return
        
        user_id = event.get_sender_id()
        stock = self.db.get_stock(stock_id)
        if not stock:
            yield event.plain_result(f"股票 {stock_id} 不存在")
            return

        result = self.db.sell_stock(user_id, stock_id, shares_int, stock["price"])
        yield event.plain_result(result["message"])

    @filter.command("持仓")
    async def portfolio(self, event: AstrMessageEvent):
        """查看持仓"""
        user_id = event.get_sender_id()
        holdings = self.db.get_user_holdings(user_id)

        if not holdings:
            yield event.plain_result("暂无持仓")
            return

        lines = ["=== 股票持仓 ==="]
        for h in holdings:
            profit = (h["current_price"] - h["avg_price"]) * h["shares"]
            profit_emoji = "📈" if profit >= 0 else "📉"
            lines.append(f"[{h['stock_id']}] {h['name']}")
            lines.append(f"  持仓: {h['shares']}股 | 成本: {h['avg_price']} | 现价: {h['current_price']}")
            lines.append(f"  {profit_emoji} 盈亏: {profit:.2f}金币")
            lines.append("")

        portfolio = self.stock_system.calculate_portfolio_value(user_id)
        lines.append(f"总资产: {portfolio['total_value']}金币")
        lines.append(f"总盈亏: {portfolio['total_profit']}金币 ({portfolio['total_profit_rate']}%)")
        yield event.plain_result("\n".join(lines))

    @filter.command("添加股票")
    async def add_stock(self, event: AstrMessageEvent, stock_id: str = "", name: str = "", price: str = ""):
        """添加股票（管理员）"""
        if not stock_id or not name or not price:
            yield event.plain_result(
                "添加股票命令用法: /添加股票 股票代码 名称 初始价格\n"
                "例如: /添加股票 BTC 比特币 50000"
            )
            return
        
        try:
            price_float = float(price)
        except ValueError:
            yield event.plain_result("价格必须是数字")
            return
        
        user_id = event.get_sender_id()
        if user_id not in self.config.get("admin_ids", []):
            yield event.plain_result("只有管理员才能添加股票")
            return

        if self.db.get_stock(stock_id):
            yield event.plain_result(f"股票 {stock_id} 已存在")
            return

        success = self.db.add_stock(stock_id, name, price_float)
        if success:
            yield event.plain_result(
                f"添加股票成功!\n"
                f"代码: {stock_id}\n"
                f"名称: {name}\n"
                f"初始价格: {price_float}金币"
            )
        else:
            yield event.plain_result("添加股票失败")

    @filter.command("删除股票")
    async def remove_stock(self, event: AstrMessageEvent, stock_id: str = ""):
        """删除股票（管理员）"""
        if not stock_id:
            yield event.plain_result(
                "删除股票命令用法: /删除股票 股票代码\n"
                "例如: /删除股票 BTC"
            )
            return
        user_id = event.get_sender_id()
        if user_id not in self.config.get("admin_ids", []):
            yield event.plain_result("只有管理员才能删除股票")
            return

        stock = self.db.get_stock(stock_id)
        if not stock:
            yield event.plain_result(f"股票 {stock_id} 不存在")
            return

        self.db.remove_stock(stock_id)
        yield event.plain_result(f"已删除股票: {stock['name']} ({stock_id})")

    # ==================== 排行榜命令 ====================

    @filter.command("排行")
    async def ranking(self, event: AstrMessageEvent, ranking_type: str = "coins"):
        """查看排行榜"""
        if ranking_type == "coins":
            result = await self.ranking_tool.call(
                None, ranking_type="coins"
            )
        elif ranking_type == "stock":
            result = await self.ranking_tool.call(
                None, ranking_type="stock"
            )
        elif ranking_type == "total":
            result = await self.ranking_tool.call(
                None, ranking_type="total"
            )
        else:
            result = "排行榜类型: coins(金币), stock(股票), total(总资产)"
        yield event.plain_result(result)

    # ==================== AI 对话命令 ====================

    @filter.command("经济")
    async def economy_chat(self, event: AstrMessageEvent, prompt: str = ""):
        """与经济系统AI助手对话"""
        if not prompt:
            yield event.plain_result(
                "你好! 我是经济系统助手，可以帮你:\n"
                "- 查询金币余额\n"
                "- 执行签到\n"
                "- 查看和购买商品\n"
                "- 进行股票交易\n"
                "- 查看排行榜\n\n"
                "请告诉我你想做什么?"
            )
            return

        umo = event.unified_msg_origin
        prov_id = await self.context.get_current_chat_provider_id(umo)

        llm_resp = await self.context.tool_loop_agent(
            event=event,
            chat_provider_id=prov_id,
            prompt=prompt,
            tools=ToolSet([
                self.balance_tool,
                self.sign_tool,
                self.shop_tool,
                self.stock_tool,
                self.ranking_tool
            ]),
            max_steps=10,
            tool_call_timeout=30,
        )
        yield event.plain_result(llm_resp.completion_text)

    async def terminate(self):
        """插件卸载时关闭数据库"""
        self.db.close()
        logger.info("经济系统插件已卸载")
