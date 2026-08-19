# -*- coding: utf-8 -*-
"""
receipt_agent.py
-----------------
LangGraph 영수증 승인 Agent (비즈니스 로직)

기존 langgraph1_receit.py 의 내용을 그대로 가져오되,
FastAPI의 `app = FastAPI()` 와 이름이 충돌하지 않도록
`app = workflow.compile()` 를 `receipt_graph = workflow.compile()` 로 변경했습니다.
"""

from typing import TypedDict
from langgraph.graph import StateGraph, START, END


# 1. 상태(State) 정의: 노드들이 공유할 데이터 주머니
class ReceiptState(TypedDict):
    item_name: str        # 항목 (예: 택시비, KTX, 식대)
    amount: int            # 청구 금액
    is_night: bool          # 야간 여부 (택시비 판단용)
    approved_amount: int   # 승인된 금액
    status: str             # 최종 상태 (승인 / 부분 승인 / 반려)
    reason: str             # 처리 사유


# 2. 노드(Node) 정의: 비즈니스 로직 처리
def node_check_policy(state: ReceiptState) -> dict:
    """[노드 1] 사내 규정에 따라 승인 가능 한도를 확인하는 노드"""
    print("\n[노드 1] 사내 출장비 규정 검토 중...")
    item = state["item_name"]
    amount = state["amount"]
    is_night = state["is_night"]

    # 가상의 규정 검토 로직
    if item == "택시비":
        if is_night:
            limit = 30000
            reason = "야간 택시비 한도 30,000원 적용"
        else:
            limit = 0
            reason = "주간 택시비는 원칙적 승인 불가"
    elif item == "식대":
        limit = 10000
        reason = "식대 한도 10,000원 적용"
    else:  # KTX, 버스 등
        limit = amount
        reason = "대중교통 실비 전액 승인"

    # 승인 가능 한도 금액을 계산하여 상태 업데이트
    approved = min(amount, limit)
    return {"approved_amount": approved, "reason": reason}


def node_calculate_status(state: ReceiptState) -> dict:
    """[노드 2] 승인 금액과 청구 금액을 비교하여 최종 상태를 결정하는 노드"""
    print("[노드 2] 최종 승인 상태 판정 중...")
    amount = state["amount"]
    approved = state["approved_amount"]

    if approved == amount and approved > 0:
        final_status = "전액 승인"
    elif approved > 0 and approved < amount:
        final_status = "부분 승인 (한도 초과)"
    else:
        final_status = "반려"

    return {"status": final_status}


# 3. 워크플로우 그래프 설계 조립
workflow = StateGraph(ReceiptState)

# 노드 등록
workflow.add_node("check_policy", node_check_policy)
workflow.add_node("calculate_status", node_calculate_status)

# 엣지(Edge) 연결: START -> check_policy -> calculate_status -> END
workflow.add_edge(START, "check_policy")
workflow.add_edge("check_policy", "calculate_status")
workflow.add_edge("calculate_status", END)

# 4. 컴파일(Compile): 설계를 기반으로 실행 가능한 애플리케이션 빌드
# 주의: FastAPI의 app = FastAPI() 와 이름이 겹치지 않도록 receipt_graph 로 명명
receipt_graph = workflow.compile()


if __name__ == "__main__":
    print("==================================================")
    print("LangGraph 초간단 파이프라인 구동 (단독 실행 테스트)")
    print("==================================================")

    initial_input: ReceiptState = {
        "item_name": "택시비",
        "amount": 35000,
        "is_night": True,
        "approved_amount": 0,
        "status": "",
        "reason": "",
    }

    final_output = receipt_graph.invoke(initial_input)

    print("==================================================")
    print("최종 결과 출력")
    print("==================================================")
    print(final_output)
