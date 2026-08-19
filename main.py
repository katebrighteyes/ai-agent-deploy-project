# -*- coding: utf-8 -*-
"""
main.py
--------
FastAPI Backend

역할: Streamlit(또는 Swagger)에서 요청을 받아 LangGraph Agent(receipt_graph)를
      실행하고 결과를 반환한다.

이번 업그레이드에서는 SSE(Server-Sent Events) 방식을 추가했습니다.
LangGraph는 `.invoke()` 대신 `.stream()`을 쓰면 노드가 끝날 때마다
중간 결과를 하나씩 흘려보낼 수 있습니다. 이걸 그대로 HTTP 응답으로
스트리밍하면, 프론트엔드는 "노드 1 처리 중 → 노드 2 처리 중 → 완료"
과정을 실시간으로 받아볼 수 있습니다.

처리 흐름 (SSE):
    Request
       ↓
    FastAPI (StreamingResponse)
       ↓
    ReceiptState 생성
       ↓
    receipt_graph.stream()  ── 노드가 끝날 때마다 이벤트 1개 전송
       ↓                         ↓                    ↓
   node_update(check_policy) node_update(...)      done(최종결과)
       ↓
    Streamlit이 실시간으로 수신하여 화면 갱신

엔드포인트:
    GET  /                     서버 동작 확인
    GET  /health                서비스 상태 확인
    POST /receipt/check         기존 방식 (한 번에 결과 반환)
    POST /receipt/check/stream  SSE 방식 (노드별로 실시간 스트리밍)

실행:
    uvicorn main:app --reload
    -> http://127.0.0.1:8000/docs 에서 Swagger UI 확인
    -> SSE 스트림은 curl -N 으로 직접 확인 가능 (README 참고)
"""

import json
import time
from typing import Generator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from receipt_agent import receipt_graph, ReceiptState
from schemas import ReceiptRequest, ReceiptResponse

# FastAPI 앱 생성
# 주의: receipt_agent.py 의 LangGraph 컴파일 결과는 `receipt_graph` 로 명명되어 있어
#       여기서 `app` 이라는 이름을 자유롭게 FastAPI 용으로 사용할 수 있다.
app = FastAPI(
    title="출장비 영수증 승인 Agent API",
    description="LangGraph 기반 영수증 승인 Agent를 REST API(+ SSE 스트리밍)로 제공합니다.",
    version="2.0.0",
)


@app.get("/")
def read_root():
    """서버 동작 확인용 기본 엔드포인트"""
    return {"message": "영수증 승인 Agent API가 정상적으로 동작 중입니다."}


@app.get("/health")
def health_check():
    """서비스 상태 확인용 엔드포인트"""
    return {"status": "ok"}


def _to_initial_state(request: ReceiptRequest) -> ReceiptState:
    """API Request -> ReceiptState 변환 (공통 로직)"""
    return {
        "item_name": request.item_name,
        "amount": request.amount,
        "is_night": request.is_night,
        "approved_amount": 0,
        "status": "",
        "reason": "",
    }


@app.post("/receipt/check", response_model=ReceiptResponse)
def check_receipt(request: ReceiptRequest):
    """[기존 방식] 영수증 승인 Agent 실행 - 완료 후 결과를 한 번에 반환

    ① 요청 수신 → ② ReceiptState 생성 → ③ receipt_graph.invoke() → ④ 결과 반환
    """
    initial_state = _to_initial_state(request)

    # ③ : LangGraph 호출 (동기적으로 끝까지 실행 후 최종 상태만 받음)
    result = receipt_graph.invoke(initial_state)

    # ④ : LangGraph State -> JSON Response 변환
    return ReceiptResponse(
        item_name=result["item_name"],
        amount=result["amount"],
        approved_amount=result["approved_amount"],
        status=result["status"],
        reason=result["reason"],
    )


def _sse_event(event: str, data: dict) -> str:
    """SSE 포맷 문자열 생성

    SSE 스펙:
        event: <이벤트 이름>
        data: <JSON 문자열>
        \n\n   ← 이벤트 구분을 위해 빈 줄 필수
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _generate_receipt_stream(request: ReceiptRequest) -> Generator[str, None, None]:
    """LangGraph 실행 과정을 SSE 이벤트로 하나씩 생성(yield)하는 제너레이터

    receipt_graph.stream()은 노드가 끝날 때마다
        {"check_policy": {...변경된 값...}}
        {"calculate_status": {...변경된 값...}}
    형태로 결과를 하나씩 돌려준다. 이를 그대로 현재 상태에 누적 반영하면서
    'node_update' 이벤트로 프론트엔드에 전송한다.
    """
    initial_state = _to_initial_state(request)
    current_state = dict(initial_state)

    # ① 시작 이벤트
    yield _sse_event("start", {"message": "영수증 검토를 시작합니다.", **current_state})

    # ② 노드가 끝날 때마다 이벤트 전송
    for step in receipt_graph.stream(initial_state):
        for node_name, node_output in step.items():
            current_state.update(node_output)
            yield _sse_event(
                "node_update",
                {"node": node_name, "output": node_output, "state": current_state},
            )
            # 교육용: 진행 과정을 눈으로 확인할 수 있도록 약간의 지연을 준다.
            time.sleep(0.6)

    # ③ 최종 결과 이벤트
    final_response = ReceiptResponse(
        item_name=current_state["item_name"],
        amount=current_state["amount"],
        approved_amount=current_state["approved_amount"],
        status=current_state["status"],
        reason=current_state["reason"],
    )
    yield _sse_event("done", final_response.model_dump())


@app.post("/receipt/check/stream")
def check_receipt_stream(request: ReceiptRequest):
    """[SSE 방식] 영수증 승인 Agent 실행 - 노드가 끝날 때마다 실시간으로 전송

    ① Streamlit에서 요청 수신
    ② ReceiptState 생성
    ③ receipt_graph.stream() 호출 → 노드 결과가 나올 때마다 SSE 이벤트 전송
    ④ 마지막에 'done' 이벤트로 최종 결과 전송
    """
    return StreamingResponse(
        _generate_receipt_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 프록시(nginx 등)가 응답을 버퍼링하지 않도록 하는 헤더 (교육용 참고)
            "X-Accel-Buffering": "no",
        },
    )
