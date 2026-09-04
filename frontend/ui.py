from __future__ import annotations

import streamlit as st


STATUS_STEPS = [
    "AWAITING_ANGLE_APPROVAL",
    "AWAITING_CONTENT_APPROVAL",
    "PUBLISH_READY",
    "AWAITING_SLIDE_APPROVAL",
    "SLIDES_APPROVED",
    "AWAITING_VIDEO_APPROVAL",
    "DONE",
]


def install_brand_details() -> None:
    st.html(
        """
        <style>
        .st-key-ekmind_hero {
            background: linear-gradient(118deg, #0C1830 0%, #17284A 72%, #263B68 100%);
            border: 1px solid #2A3C62;
            border-radius: 18px;
            color: #FFF8E7;
            margin: 0 0 1.35rem 0;
            overflow: hidden;
            padding: 1.35rem 1.6rem 1.45rem 1.6rem;
            position: relative;
        }
        .st-key-ekmind_hero::after {
            background: #F4B21A;
            content: "";
            height: 7px;
            left: 0;
            position: absolute;
            right: 0;
            top: 0;
        }
        .st-key-ekmind_hero h1 {color: #FFF8E7; letter-spacing: -.035em; padding: 0;}
        .st-key-ekmind_hero p {color: #E9E3D4; margin-bottom: 0;}
        .ekmind-kicker {
            color: #F4B21A;
            font-size: .72rem;
            font-weight: 800;
            letter-spacing: .14em;
            margin-bottom: .42rem;
            text-transform: uppercase;
        }
        .ekmind-progress {color: #72521A; font-size: .78rem; font-weight: 700; letter-spacing: .035em; margin: .1rem 0 .4rem;}
        </style>
        """
    )


def page_header(title: str, subtitle: str, kicker: str = "Ekmind · AI content studio") -> None:
    with st.container(key="ekmind_hero"):
        st.html(f'<div class="ekmind-kicker">{kicker}</div>')
        st.title(title)
        st.write(subtitle)


def workflow_progress(session: dict | None) -> None:
    if not session:
        st.html('<div class="ekmind-progress">01 BRIEF · 02 STRATEGY · 03 POST · 04 SLIDES · 05 VIDEO</div>')
        st.progress(0, text="Start with a topic and audience")
        return
    status = session.get("status", STATUS_STEPS[0])
    try:
        index = STATUS_STEPS.index(status)
    except ValueError:
        index = 0
    percent = int(((index + 1) / len(STATUS_STEPS)) * 100)
    label = status.replace("_", " ").title()
    st.html('<div class="ekmind-progress">STRATEGY → POST → SLIDES → VIDEO → APPROVAL</div>')
    st.progress(percent, text=label)
