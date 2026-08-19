from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class StockTool(FunctionTool[AstrAgentContext]):
    """股票交易工具，支持查询股票、买入、卖出和查看持仓。"""

    name: str = "stock_operation"
    description: str = "股票交易操作：查询股票信息、买入、卖出或查看持仓"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["query", "buy", "sell", "portfolio", "add", "remove"],
                    "description": "操作类型：query查询股票，buy买入，sell卖出，portfolio查看持仓，add添加股票(管理员)，remove删除股票(管理员)",
                },
                "user_id": {
                    "type": "string",
                    "description": "操作用户ID（buy/sell/portfolio操作时需要）",
                },
                "stock_id": {
                    "type": "string",
                    "description": "股票代码（query单只/buy/sell操作时需要）",
                },
                "shares": {
                    "type": "integer",
                    "description": "交易数量（buy/sell操作时需要）",
                },
                "name": {
                    "type": "string",
                    "description": "股票名称（add操作时需要）",
                },
                "price": {
                    "type": "number",
                    "description": "初始价格（add操作时需要）",
                },
            },
            "required": ["action"],
        }
    )

    db = None  # 将在 main.py 中设置
    stock_system = None  # 将在 main.py 中设置
    admin_ids = []  # 管理员列表

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        action = kwargs["action"]

        if action == "query":
            return self._query_stock(kwargs.get("stock_id"))
        elif action == "buy":
            return self._buy_stock(kwargs["user_id"], kwargs["stock_id"], kwargs["shares"])
        elif action == "sell":
            return self._sell_stock(kwargs["user_id"], kwargs["stock_id"], kwargs["shares"])
        elif action == "portfolio":
            return self._query_portfolio(kwargs["user_id"])
        elif action == "add":
            return self._add_stock(kwargs)
        elif action == "remove":
            return self._remove_stock(kwargs)
        else:
            return "未知操作"

    def _query_stock(self, stock_id: str = None) -> str:
        """查询股票信息"""
        if stock_id:
            # 查询单只股票
            info = self.stock_system.get_stock_info(stock_id)
            if not info:
                return f"股票 {stock_id} 不存在"

            lines = [
                f"=== {info['name']} ({info['stock_id']}) ===",
                f"当前价格: {info['price']}金币",
                f"基准价格: {info['base_price']}金币",
                f"涨跌幅: {info['change']}% {info['trend_emoji']}",
                f"趋势: {info['trend']}",
                f"最后更新: {info['last_update']}"
            ]
            return "\n".join(lines)
        else:
            # 查询所有股票
            stocks = self.stock_system.get_all_stocks_info()
            if not stocks:
                return "暂无股票"

            lines = ["=== 股票列表 ==="]
            for s in stocks:
                lines.append(f"[{s['stock_id']}] {s['name']}")
                lines.append(f"  价格: {s['price']}金币 | 涨跌: {s['change']}% {s['trend_emoji']}")
            return "\n".join(lines)

    def _buy_stock(self, user_id: str, stock_id: str, shares: int) -> str:
        """买入股票"""
        stock = self.db.get_stock(stock_id)
        if not stock:
            return f"股票 {stock_id} 不存在"

        result = self.db.buy_stock(user_id, stock_id, shares, stock["price"])
        return result["message"]

    def _sell_stock(self, user_id: str, stock_id: str, shares: int) -> str:
        """卖出股票"""
        stock = self.db.get_stock(stock_id)
        if not stock:
            return f"股票 {stock_id} 不存在"

        result = self.db.sell_stock(user_id, stock_id, shares, stock["price"])
        return result["message"]

    def _query_portfolio(self, user_id: str) -> str:
        """查询持仓"""
        portfolio = self.stock_system.calculate_portfolio_value(user_id)
        holdings = self.db.get_user_holdings(user_id)

        if not holdings:
            return "暂无持仓"

        lines = ["=== 股票持仓 ==="]
        for h in holdings:
            profit_emoji = "📈" if h.get("current_price", 0) > h.get("avg_price", 0) else "📉"
            lines.append(f"[{h['stock_id']}] {h['name']}")
            lines.append(f"  持仓: {h['shares']}股 | 成本: {h['avg_price']} | 现价: {h['current_price']}")
            lines.append(f"  {profit_emoji}")

        lines.append("")
        lines.append(f"总资产: {portfolio['total_value']}金币")
        lines.append(f"总盈亏: {portfolio['total_profit']}金币 ({portfolio['total_profit_rate']}%)")
        return "\n".join(lines)

    def _add_stock(self, kwargs: dict) -> str:
        """添加新股票"""
        user_id = kwargs.get("user_id", "")
        if user_id not in self.admin_ids:
            return "只有管理员才能添加股票"

        stock_id = kwargs.get("stock_id", "")
        name = kwargs.get("name", "")
        price = kwargs.get("price", 0)

        if not stock_id or not name or price <= 0:
            return "股票代码、名称和价格必须有效"

        if self.db.get_stock(stock_id):
            return f"股票 {stock_id} 已存在"

        success = self.db.add_stock(stock_id, name, float(price))
        if success:
            return f"添加股票成功! 代码: {stock_id}, 名称: {name}, 初始价格: {price}金币"
        else:
            return "添加股票失败"

    def _remove_stock(self, kwargs: dict) -> str:
        """删除股票"""
        user_id = kwargs.get("user_id", "")
        if user_id not in self.admin_ids:
            return "只有管理员才能删除股票"

        stock_id = kwargs.get("stock_id", "")
        if not stock_id:
            return "请提供股票代码"

        stock = self.db.get_stock(stock_id)
        if not stock:
            return f"股票 {stock_id} 不存在"

        self.db.remove_stock(stock_id)
        return f"已删除股票: {stock['name']} ({stock_id})"
