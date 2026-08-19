from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class ShopTool(FunctionTool[AstrAgentContext]):
    """商店操作工具，支持查询商品和购买商品。"""

    name: str = "shop_operation"
    description: str = "商店操作：查询商品列表或购买商品"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["query", "buy", "add", "remove"],
                    "description": "操作类型：query查询商品，buy购买商品，add上架商品(管理员)，remove下架商品(管理员)",
                },
                "user_id": {
                    "type": "string",
                    "description": "操作用户ID（buy操作时需要）",
                },
                "item_id": {
                    "type": "integer",
                    "description": "商品ID（buy操作时需要）",
                },
                "name": {
                    "type": "string",
                    "description": "商品名称（add操作时需要）",
                },
                "price": {
                    "type": "integer",
                    "description": "商品价格（add操作时需要）",
                },
                "description": {
                    "type": "string",
                    "description": "商品描述（add操作时需要）",
                },
                "stock": {
                    "type": "integer",
                    "description": "库存数量（add操作时可选，默认999）",
                },
            },
            "required": ["action"],
        }
    )

    db = None  # 将在 main.py 中设置
    admin_ids = []  # 管理员列表

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        action = kwargs["action"]

        if action == "query":
            return self._query_items(kwargs.get("category"))
        elif action == "buy":
            return self._buy_item(kwargs["user_id"], kwargs["item_id"])
        elif action == "add":
            return self._add_item(kwargs)
        elif action == "remove":
            return self._remove_item(kwargs)
        else:
            return "未知操作"

    def _query_items(self, category: str = None) -> str:
        """查询商品列表"""
        items = self.db.get_shop_items(category)
        if not items:
            return "商店暂时没有商品"

        lines = ["=== 商店商品列表 ==="]
        for item in items:
            lines.append(f"[ID:{item['item_id']}] {item['name']}")
            lines.append(f"  价格: {item['price']}金币 | 库存: {item['stock']}")
            if item['description']:
                lines.append(f"  描述: {item['description']}")
            lines.append("")
        return "\n".join(lines)

    def _buy_item(self, user_id: str, item_id: int) -> str:
        """购买商品"""
        result = self.db.buy_shop_item(item_id, user_id)
        return result["message"]

    def _add_item(self, kwargs: dict) -> str:
        """上架商品"""
        user_id = kwargs.get("user_id", "")
        if user_id not in self.admin_ids:
            return "只有管理员才能上架商品"

        name = kwargs.get("name", "")
        price = kwargs.get("price", 0)
        description = kwargs.get("description", "")
        stock = kwargs.get("stock", 999)

        if not name or price <= 0:
            return "商品名称和价格必须有效"

        item_id = self.db.add_shop_item(
            name=name,
            price=price,
            description=description,
            stock=stock,
            added_by=user_id
        )
        return f"上架商品成功! 商品ID: {item_id}, 名称: {name}, 价格: {price}金币"

    def _remove_item(self, kwargs: dict) -> str:
        """下架商品"""
        user_id = kwargs.get("user_id", "")
        if user_id not in self.admin_ids:
            return "只有管理员才能下架商品"

        item_id = kwargs.get("item_id")
        if not item_id:
            return "请提供商品ID"

        item = self.db.get_shop_item(item_id)
        if not item:
            return f"商品 {item_id} 不存在"

        self.db.remove_shop_item(item_id)
        return f"已下架商品: {item['name']} (ID: {item_id})"
