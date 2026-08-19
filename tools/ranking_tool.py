from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class RankingTool(FunctionTool[AstrAgentContext]):
    """查询排行榜工具，支持金币排行榜和股票资产排行榜。"""

    name: str = "query_ranking"
    description: str = "查询排行榜：金币排行榜、股票资产排行榜或总资产排行榜"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "ranking_type": {
                    "type": "string",
                    "enum": ["coins", "stock", "total"],
                    "description": "排行榜类型：coins金币排行，stock股票资产排行，total总资产排行",
                },
                "limit": {
                    "type": "integer",
                    "description": "显示前N名，默认10",
                },
            },
            "required": ["ranking_type"],
        }
    )

    db = None  # 将在 main.py 中设置
    stock_system = None  # 将在 main.py 中设置

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        ranking_type = kwargs["ranking_type"]
        limit = kwargs.get("limit", 10)

        if ranking_type == "coins":
            return self._coins_ranking(limit)
        elif ranking_type == "stock":
            return self._stock_ranking(limit)
        elif ranking_type == "total":
            return self._total_ranking(limit)
        else:
            return "未知排行榜类型"

    def _coins_ranking(self, limit: int) -> str:
        """金币排行榜"""
        ranking = self.db.get_coins_ranking(limit)
        if not ranking:
            return "暂无数据"

        lines = ["=== 金币排行榜 ==="]
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(ranking):
            medal = medals[i] if i < 3 else f" {i+1}."
            lines.append(f"{medal} {r['user_id']}: {r['coins']}金币")
        return "\n".join(lines)

    def _stock_ranking(self, limit: int) -> str:
        """股票资产排行榜"""
        ranking = self.db.get_stock_ranking(limit)
        if not ranking:
            return "暂无数据"

        lines = ["=== 股票资产排行榜 ==="]
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(ranking):
            medal = medals[i] if i < 3 else f" {i+1}."
            lines.append(f"{medal} {r['user_id']}: {r['total_value']:.2f}金币")
        return "\n".join(lines)

    def _total_ranking(self, limit: int) -> str:
        """总资产排行榜"""
        ranking = self.db.get_total_assets_ranking(limit)
        if not ranking:
            return "暂无数据"

        lines = ["=== 总资产排行榜 ==="]
        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(ranking):
            medal = medals[i] if i < 3 else f" {i+1}."
            lines.append(f"{medal} {r['user_id']}: {r['total_assets']:.2f}金币")
        return "\n".join(lines)
