import streamlit as st
from client import get, post
from ui import page_header, workflow_progress

page_header("Content studio", "Turn one useful idea into a researched post, an editable presentation, and a presenter-led video.")
workflow_progress(st.session_state.get("session"))
if st.session_state.get("session") and st.button("Start a new session", icon=":material/add:"):
    del st.session_state["session"]
    st.rerun()
strategy, post_tab, slides, video, evaluation = st.tabs([":material/strategy: Strategy", ":material/article: Post", ":material/slideshow: Slides", ":material/movie: Video", ":material/analytics: Evaluation"])
with strategy:
    with st.container(border=True):
      with st.form("strategy_form", border=False):
        st.subheader("Shape the brief")
        st.caption("Give the studio a focused idea. Research and quality controls are applied automatically.")
        topic = st.text_area("Topic or idea", placeholder="What should the thought-leadership post explore?", key="topic")
        c1, c2, c3 = st.columns(3)
        objective = c1.selectbox("Objective", ["Thought Leadership", "Educational", "Technical", "Opinion", "Announcement"])
        audience = c2.selectbox("Audience", ["SAP Consultants", "HR Leaders", "HR Technology Leaders", "Executives", "General Professional Audience", "Custom"])
        tone = c3.selectbox("Tone", ["Professional", "Practitioner", "Educational", "Contrarian", "Conversational"])
        c4, c5 = st.columns(2)
        research_mode = c4.segmented_control("Research", ["Auto", "Always", "Skip"], default="Auto")
        target_length = c5.segmented_control("Length", ["Short", "Medium", "Long"], default="Medium")
        submitted = st.form_submit_button("Generate content strategy", type="primary", icon=":material/auto_awesome:")
    if submitted:
        try:
            st.session_state.session = post("/api/sessions", {"topic": topic, "objective": objective, "audience": audience, "tone": tone, "research_mode": research_mode, "target_length": target_length})
        except Exception as exc:
            st.error(f"Backend unavailable: {exc}")
    session = st.session_state.get("session")
    if session:
        with st.status("Strategy ready", state="complete"):
            st.write(session["planner"]["reason_research_required"])
            if session.get("research_sources"):
                st.write(f"Retrieved {len(session['research_sources'])} sources")
                for source in session["research_sources"]:
                    st.markdown(f"- [{source['source_title']}]({source['source_url']}) — {source['publisher']}")
        st.subheader("Chosen angle" if session.get("angle_approved") else "Choose one angle")
        columns = st.columns(3)
        for column, angle in zip(columns, session["candidate_angles"]):
            with column.container(border=True, height="stretch"):
                st.subheader(angle["angle_type"])
                st.write(angle["hook"])
                st.caption(angle["thesis"])
                st.metric("Novelty", f"{angle['novelty_score']:.1f}/10")
                selected = session.get("selected_angle", {}).get("angle_id") == angle["angle_id"] if session.get("selected_angle") else False
                if selected:
                    st.success("Selected")
                if st.button("Select and approve", key=angle["angle_id"], icon=":material/check_circle:", disabled=session.get("angle_approved", False)):
                    try:
                        st.session_state.session = post(f"/api/sessions/{session['session_id']}/approve-angle", {"angle_id": angle["angle_id"]})
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not approve angle: {exc}")
        if not session.get("angle_approved"):
            angle_reason = st.text_input("Reason for rejecting these angles (optional)", key="angle_reject_reason")
            if st.button("Reject all and regenerate", icon=":material/refresh:"):
                try:
                    st.session_state.session = post(f"/api/sessions/{session['session_id']}/reject-angles", {"reason": angle_reason})
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not reject angles: {exc}")
with post_tab:
    session = st.session_state.get("session")
    if not session or not session.get("angle_approved"):
        st.warning("Approve an angle in Strategy to unlock the post.")
    else:
        left, right = st.columns([2, 1])
        with left:
            edited = st.text_area("LinkedIn post", value=session["current_draft"], height=480, key="post_editor")
            content_reason = st.text_input("Rejection reason (optional)", key="content_reject_reason")
            with st.container(horizontal=True):
                if st.button("Approve content", type="primary", disabled=session.get("content_approved", False), icon=":material/verified:"):
                    try:
                        st.session_state.session = post(f"/api/sessions/{session['session_id']}/approve-content", {"edited_content": edited})
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not approve content: {exc}")
                if st.button("Reject content", disabled=session.get("content_approved", False), icon=":material/cancel:"):
                    try:
                        st.session_state.session = post(f"/api/sessions/{session['session_id']}/reject-content", {"reason": content_reason})
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not reject content: {exc}")
        with right.container(border=True):
            st.subheader("Evaluation summary")
            for name, status in session["evaluation_groups"].items():
                st.write(f"**{name}:** {status}")
            if session.get("critique"):
                keys = ["clarity", "value", "engagement", "tone", "originality", "voice_match", "audience_relevance"]
                st.metric("Critic score", f"{sum(session['critique'][key] for key in keys)/len(keys):.1f}/10")
            if session.get("content_approved"):
                st.success("Content approved — PUBLISH READY")
with slides:
    session = st.session_state.get("session")
    if not session or not session.get("content_approved"):
        st.warning("Approve content before generating slides.")
    else:
        slide_brief = st.text_area(
            "Slide design note",
            value="Be creative and visual-led. Use varied layouts, relevant visuals, diagrams or charts where they strengthen the message. Keep copy concise and ensure every element fits safely inside the slide frame without clipping or overlap.",
            height=110,
            key="slide_design_note",
        )
        if not session.get("pptx_path") and st.button("Generate slides", type="primary", icon=":material/slideshow:"):
            try:
                with st.spinner("Designing a creative, visual-led deck and checking slide fit..."):
                    st.session_state.session = post(f"/api/sessions/{session['session_id']}/slides", {"design_instructions": slide_brief})
                st.rerun()
            except Exception as exc:
                st.error(f"Could not generate slides: {exc}")
        if session.get("slide_previews"):
            st.subheader("Slide previews")
            cols = st.columns(4)
            for i, preview in enumerate(session["slide_previews"]):
                cols[i % 4].image(preview, caption=f"Slide {i + 1}")
            with open(session["pptx_path"], "rb") as deck:
                st.download_button("Download PPTX", deck, file_name="ekmind-content-deck.pptx", mime="application/vnd.openxmlformats-officedocument.presentationml.presentation", icon=":material/download:")
            if not session.get("slides_approved"):
                slide_reason = st.text_input("Slide rejection reason (optional)", key="slide_reject_reason")
                with st.container(horizontal=True):
                    if st.button("Approve slides", type="primary", icon=":material/verified:"):
                        try:
                            st.session_state.session = post(f"/api/sessions/{session['session_id']}/approve-slides", {})
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not approve slides: {exc}")
                    if st.button("Reject slides", icon=":material/cancel:"):
                        try:
                            st.session_state.session = post(f"/api/sessions/{session['session_id']}/reject-slides", {"reason": slide_reason})
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not reject slides: {exc}")
            if session.get("slides_approved"):
                st.success("Slides approved. Video generation is unlocked.")
with video:
    session = st.session_state.get("session")
    if not session or not session.get("slides_approved"):
        st.warning("Approve slides before generating video.")
    else:
        try:
            media_capabilities = get("/health")["capabilities"]
            avatar_provider = media_capabilities["avatar"]
            youtube_configured = media_capabilities.get("youtube") == "configured"
        except Exception:
            avatar_provider = "unknown"
            youtube_configured = False
        paid_render = avatar_provider == "heygen"
        if paid_render:
            reusable_avatar = bool(session.get("video_path") and session.get("video_validation", {}).get("source_duration_seconds"))
            if reusable_avatar:
                st.info("The existing HeyGen presenter clip will be recomposed locally, so regeneration will not consume new HeyGen credits.")
            else:
                st.info("HeyGen is connected. The finished video will combine your approved slides with the configured avatar and voice.")
            confirm_paid_render = st.checkbox("I understand this will use HeyGen credits" if not reusable_avatar else "Recompose using the existing HeyGen presenter clip", key="confirm_paid_render")
        else:
            st.info("Avatar and voice providers: mock. No paid external API will be called.")
            confirm_paid_render = False
        if not session.get("video_path") and st.button("Generate video", type="primary", icon=":material/movie:", disabled=paid_render and not confirm_paid_render):
            try:
                with st.spinner("Generating the avatar and composing it with your approved slides. This can take several minutes..."):
                    st.session_state.session = post(f"/api/sessions/{session['session_id']}/video", {"confirm_paid_render": confirm_paid_render}, timeout=1300)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not generate video: {exc}")
        if session.get("video_path"):
            st.video(session["video_path"])
            st.json(session["video_validation"])
            with open(session["subtitle_path"], "rb") as captions:
                st.download_button("Download captions", captions, file_name="captions.srt", mime="text/plain", icon=":material/subtitles:")
            if st.button("Regenerate video from slides", icon=":material/refresh:", disabled=paid_render and not confirm_paid_render):
                try:
                    with st.spinner("Recomposing approved slides..."):
                        st.session_state.session = post(f"/api/sessions/{session['session_id']}/video", {"confirm_paid_render": confirm_paid_render}, timeout=1300)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not regenerate video: {exc}")
            if not session.get("video_approved"):
                video_reason = st.text_input("Video rejection reason (optional)", key="video_reject_reason")
                with st.container(border=True):
                    st.subheader("Final publishing")
                    if youtube_configured:
                        publish_to_youtube = st.checkbox(
                            "Upload this video privately to YouTube after approval",
                            value=True,
                            key="publish_to_youtube",
                        )
                        st.caption("Private means only you and people you explicitly share it with can view it.")
                        youtube_title = st.text_input(
                            "YouTube title",
                            value=f"Ekmind — {session['request']['topic']}"[:100],
                            max_chars=100,
                            disabled=not publish_to_youtube,
                        )
                        youtube_description = st.text_area(
                            "YouTube description",
                            value=(session.get("approved_content") or "")[:5000],
                            height=140,
                            max_chars=5000,
                            disabled=not publish_to_youtube,
                        )
                    else:
                        publish_to_youtube = False
                        youtube_title = ""
                        youtube_description = ""
                        st.info("YouTube OAuth is not configured. Approval will finish locally without uploading.", icon=":material/info:")
                with st.container(horizontal=True):
                    approve_label = "Approve and upload privately" if publish_to_youtube else "Approve video"
                    if st.button(approve_label, type="primary", icon=":material/verified:"):
                        try:
                            with st.spinner("Uploading privately to YouTube..." if publish_to_youtube else "Approving final package..."):
                                st.session_state.session = post(
                                    f"/api/sessions/{session['session_id']}/approve-video",
                                    {
                                        "publish_to_youtube": publish_to_youtube,
                                        "youtube_title": youtube_title or None,
                                        "youtube_description": youtube_description or None,
                                    },
                                    timeout=1300,
                                )
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not approve video: {exc}")
                    if st.button("Reject video", icon=":material/cancel:"):
                        try:
                            st.session_state.session = post(f"/api/sessions/{session['session_id']}/reject-video", {"reason": video_reason})
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not reject video: {exc}")
            if session.get("video_approved"):
                st.success("Final package approved — DONE")
                youtube_publish = session.get("youtube_publish", {})
                if youtube_publish.get("status") == "uploaded":
                    st.success("Uploaded to YouTube as Private", icon=":material/lock:")
                    st.link_button("Open private video", youtube_publish["watch_url"], icon=":material/open_in_new:")
with evaluation:
    session = st.session_state.get("session")
    if session:
        for name, status in session["evaluation_groups"].items():
            st.metric(name, status)
    else:
        st.info("Generate a strategy to begin evaluation tracking.")
