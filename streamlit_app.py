# -*- coding: utf-8 -*-
"""
streamlit_app.py
------------------
Streamlit Frontend (SSE 버전)

Streamlit은 Agent를 직접 실행하지 않는다.
    Streamlit -> requests.post(stream=True) -> FastAPI(SSE) -> (LangGraph) -> 이벤트 스트림

기존에는 결과가 한 번에 딱 돌아왔다면, 이번에는 FastAPI가
`/receipt/check/stream` 에서 노드가 끝날 때마다 이벤트를 하나씩 보내주고,
Streamlit은 그걸 실시간으로 받아 화면을 갱신한다.

실행:
    streamlit run streamlit_app.py

주의: FastAPI 서버(main.py)가 먼저 실행되어 있어야 한다.
    uvicorn main:app --reload
"""

import json

# import requests
# import streamlit as st

# # FastAPI 서버 주소 (SSE 스트리밍 엔드포인트)
# STREAM_API_URL = "http://127.0.0.1:8001/receipt/check/stream"

import os

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
STREAM_API_URL = f"{API_BASE_URL}/receipt/check/stream"


# 노드 이름 -> 화면에 보여줄 한글 설명
NODE_LABELS = {
    "check_policy": "① 사내 출장비 규정 검토",
    "calculate_status": "② 최종 승인 상태 판정",
}

st.set_page_config(page_title="출장비 승인 Agent (SSE)", page_icon="🧾")

st.title("🧾 출장비 승인 Agent")
st.caption("FastAPI SSE 스트리밍으로 LangGraph 노드 진행 상황을 실시간으로 보여줍니다.")
st.divider()

# ── 입력 영역 ──────────────────────────────────────
item_name = st.selectbox("항목", ["택시비", "식대", "KTX", "버스"])
amount = st.number_input("청구 금액", min_value=0, step=1000, value=35000)
is_night = st.checkbox("야간 이용")

if st.button("승인 요청"):
    payload = {
        "item_name": item_name,
        "amount": int(amount),
        "is_night": is_night,
    }

    status_box = st.empty()
    progress_box = st.container()
    result_box = st.empty()

    completed_steps = []

    try:
        # stream=True 로 요청해야 응답을 조금씩 받을 수 있다.
        with requests.post(STREAM_API_URL, json=payload, stream=True, timeout=30) as response:
            response.raise_for_status()

            status_box.info("영수증 검토 요청을 보냈습니다. 진행 상황을 기다리는 중...")

            event_type = None
            # SSE는 "event: xxx" 줄과 "data: {...}" 줄이 한 쌍으로 오고, 빈 줄로 구분된다.
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    # 이벤트 구분용 빈 줄 → 다음 이벤트를 위해 초기화
                    event_type = None
                    continue

                if raw_line.startswith("event:"):
                    event_type = raw_line.split(":", 1)[1].strip()

                elif raw_line.startswith("data:"):
                    data_str = raw_line.split(":", 1)[1].strip()
                    data = json.loads(data_str)

                    if event_type == "start":
                        status_box.info("🚀 영수증 검토를 시작합니다...")

                    elif event_type == "node_update":
                        node = data["node"]
                        label = NODE_LABELS.get(node, node)
                        completed_steps.append(label)
                        status_box.info(f"⏳ 처리 중... 방금 완료: {label}")
                        with progress_box:
                            st.write(f"✅ {label} 완료")

                    elif event_type == "done":
                        status_box.success("🎉 검토가 완료되었습니다!")
                        with result_box.container():
                            st.subheader("승인 결과")
                            st.write(f"**청구금액** : {data['amount']:,}원")
                            st.write(f"**승인금액** : {data['approved_amount']:,}원")
                            st.write(f"**결과** : {data['status']}")
                            st.write(f"**사유** : {data['reason']}")

    except requests.exceptions.ConnectionError:
        st.error("FastAPI 서버에 연결할 수 없습니다. `uvicorn main:app --reload` 로 서버를 먼저 실행해주세요.")
    except requests.exceptions.RequestException as e:
        st.error(f"요청 중 오류가 발생했습니다: {e}")
