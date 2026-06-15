"""Phase 1 工具调用状态机：强制顺序与终止条件。"""

from __future__ import annotations

from enum import Enum

from aarrr_agent.errors import PipelineError

WRITE_TOOLS = frozenset({"write_pdf_report", "write_structured_report"})
REQUIRED_TOOLS = frozenset(
    {"read_text", "read_pdf", "extract_evidence_pack"} | WRITE_TOOLS
)
OPTIONAL_TOOLS = frozenset({"self_check_report"})
ALLOWED_TOOLS = REQUIRED_TOOLS | OPTIONAL_TOOLS


class Phase1State(str, Enum):
    START = "start"
    NEED_PDF = "need_pdf"
    NEED_EVIDENCE = "need_evidence"
    NEED_REPORT = "need_report"
    DONE = "done"


class Phase1StateMachine:
    """轻量状态机：约束工具调用顺序，write 后禁止继续调工具。"""

    def __init__(self) -> None:
        self.state = Phase1State.START
        self.called_tools: list[str] = []
        self.write_tool: str | None = None

    def allowed_tools(self) -> frozenset[str]:
        if self.state == Phase1State.START:
            return frozenset({"read_text"})
        if self.state == Phase1State.NEED_PDF:
            return frozenset({"read_pdf"})
        if self.state == Phase1State.NEED_EVIDENCE:
            return frozenset({"extract_evidence_pack"})
        if self.state == Phase1State.NEED_REPORT:
            return frozenset({"self_check_report"}) | WRITE_TOOLS
        return frozenset()

    def assert_tool_allowed(self, tool_name: str) -> None:
        if tool_name not in ALLOWED_TOOLS:
            raise PipelineError("E003", f"Phase 1 不允许调用工具: {tool_name}")
        if self.state == Phase1State.DONE:
            raise PipelineError(
                "E003",
                f"报告已写入（{self.write_tool}），禁止继续调用工具: {tool_name}",
            )
        allowed = self.allowed_tools()
        if tool_name not in allowed:
            raise PipelineError(
                "E003",
                f"工具顺序错误：当前状态 {self.state.value}，不允许 {tool_name}。"
                f"允许: {', '.join(sorted(allowed)) or '无'}",
            )

    def record_tool(self, tool_name: str) -> None:
        self.assert_tool_allowed(tool_name)
        self.called_tools.append(tool_name)

        if tool_name == "read_text":
            self.state = Phase1State.NEED_PDF
        elif tool_name == "read_pdf":
            self.state = Phase1State.NEED_EVIDENCE
        elif tool_name == "extract_evidence_pack":
            self.state = Phase1State.NEED_REPORT
        elif tool_name in WRITE_TOOLS:
            self.write_tool = tool_name
            self.state = Phase1State.DONE

    def assert_complete(self, *, phase1_done: bool) -> None:
        missing = REQUIRED_TOOLS - set(self.called_tools)
        if self.write_tool:
            missing -= WRITE_TOOLS - {self.write_tool}
        if missing:
            raise PipelineError("E003", f"Agent 未调用必要工具: {', '.join(sorted(missing))}")
        if self.state != Phase1State.DONE:
            raise PipelineError("E003", "Agent 未完成报告写入")
        if not phase1_done:
            raise PipelineError("E003", "Agent 未输出 PHASE1_DONE 确认完成")
