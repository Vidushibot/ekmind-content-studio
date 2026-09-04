from urllib.parse import urlparse

import httpx
from langsmith.wrappers import wrap_openai
from openai import OpenAI
from pydantic import BaseModel, Field

from backend.schemas.content import Angle, CritiqueResult, Evidence, GenerateRequest, Slide


class AngleSet(BaseModel):
    angles: list[Angle] = Field(min_length=3, max_length=3)


class SlideDeckPlan(BaseModel):
    slides: list[Slide] = Field(min_length=8, max_length=8)


def _openai_client(api_key: str):
    """Return an OpenAI client whose calls become child spans in LangSmith."""
    return wrap_openai(OpenAI(api_key=api_key))


def search_web(query: str, api_key: str) -> list[Evidence]:
    response = httpx.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query, "search_depth": "basic", "max_results": 5, "include_answer": False},
        timeout=45,
    )
    response.raise_for_status()
    evidence = []
    query_terms = {token.casefold() for token in query.split() if len(token) > 3}
    for rank, item in enumerate(response.json().get("results", []), 1):
        url = str(item.get("url", ""))
        content = str(item.get("content", "")).strip()
        if not url or not content:
            continue
        provider_score = max(0.0, min(1.0, float(item.get("score") or 0.0)))
        content_terms = {token.casefold().strip(".,:;!?()[]") for token in f"{item.get('title', '')} {content}".split()}
        lexical_score = len(query_terms & content_terms) / max(1, len(query_terms))
        relevance_score = round(max(provider_score, lexical_score), 3)
        relevance_label = "RELEVANT" if relevance_score >= 0.5 else "PARTIALLY_RELEVANT" if relevance_score >= 0.25 else "NOT_RELEVANT"
        evidence.append(Evidence(claim=content[:1000], source_title=str(item.get("title") or url), source_url=url, publisher=urlparse(url).netloc.removeprefix("www."), confidence=provider_score or 0.5, verification_status="RETRIEVED", retrieval_rank=rank, relevance_score=relevance_score, relevance_label=relevance_label))
    return evidence


def _context(evidence: list[Evidence]) -> str:
    if not evidence:
        return "No external sources were required or available. Avoid time-sensitive facts and statistics."
    return "\n\n".join(f"SOURCE {i}: {item.source_title}\nURL: {item.source_url}\nEVIDENCE: {item.claim}" for i, item in enumerate(evidence, 1))


def generate_angles(request: GenerateRequest, evidence: list[Evidence], api_key: str, model: str) -> list[Angle]:
    response = _openai_client(api_key).responses.parse(
        model=model,
        instructions="You are a senior B2B thought-leadership strategist. Produce exactly three genuinely distinct, specific angles. Ground factual claims only in the supplied research. Do not invent statistics.",
        input=f"Topic: {request.topic}\nObjective: {request.objective}\nAudience: {request.audience}\nTone: {request.tone}\n\nResearch:\n{_context(evidence)}",
        text_format=AngleSet,
    )
    if not response.output_parsed:
        raise RuntimeError("OpenAI did not return usable content angles")
    return response.output_parsed.angles


def write_post(request: GenerateRequest, angle: Angle, evidence: list[Evidence], api_key: str, model: str) -> str:
    length = {"Short": "120-180", "Medium": "220-350", "Long": "400-600"}.get(request.target_length, "220-350")
    response = _openai_client(api_key).responses.create(
        model=model,
        instructions="Write a polished LinkedIn thought-leadership post in a credible practitioner voice. Avoid generic AI clichés. Use only supplied evidence for factual claims. Never use a number or percentage unless it appears verbatim in the supplied evidence. When research is used, cite sources inline as [Source title](URL). Return only the post.",
        input=f"Target length: {length} words\nAudience: {request.audience}\nTone: {request.tone}\nTopic: {request.topic}\nApproved angle: {angle.model_dump_json()}\n\nResearch:\n{_context(evidence)}",
    )
    return response.output_text.strip()


def critique_post(post: str, request: GenerateRequest, api_key: str, model: str) -> CritiqueResult:
    response = _openai_client(api_key).responses.parse(
        model=model,
        instructions="Act as a strict editor. Score the supplied LinkedIn post for a senior professional audience. Scores must be from 0 to 10. Required changes must be concrete.",
        input=f"Audience: {request.audience}\nTone: {request.tone}\n\nPOST:\n{post}",
        text_format=CritiqueResult,
    )
    if not response.output_parsed:
        raise RuntimeError("OpenAI did not return a usable critique")
    return response.output_parsed


def revise_post(post: str, critique: CritiqueResult, request: GenerateRequest, evidence: list[Evidence], api_key: str, model: str) -> str:
    response = _openai_client(api_key).responses.create(
        model=model,
        instructions="Revise the post to address the critique. Preserve valid citations and never invent facts. Never introduce a number or percentage unless it appears verbatim in the supplied evidence. Return only the revised post.",
        input=f"Audience: {request.audience}\nTone: {request.tone}\nRequired changes: {critique.required_changes}\n\nResearch:\n{_context(evidence)}\n\nPOST:\n{post}",
    )
    return response.output_text.strip()


def repair_grounding(post: str, unsupported: list[str], evidence: list[Evidence], api_key: str, model: str) -> str:
    response = _openai_client(api_key).responses.create(
        model=model,
        instructions="Repair the post by removing or accurately rewriting every unsupported claim. Use only the supplied evidence. If evidence does not explicitly support a statistic, remove the statistic. Preserve the post's voice and valid Markdown citations. Return only the repaired post.",
        input=f"UNSUPPORTED CLAIMS:\n" + "\n".join(f"- {claim}" for claim in unsupported) + f"\n\nEVIDENCE:\n{_context(evidence)}\n\nPOST:\n{post}",
    )
    return response.output_text.strip()


def generate_slide_plan(topic: str, post: str, design_instructions: str, api_key: str, model: str) -> list[Slide]:
    response = _openai_client(api_key).responses.parse(
        model=model,
        instructions=(
            "You are an expert presentation editor. Create exactly eight slides with a clear narrative arc. "
            "Every title and bullet must be a complete thought—never truncate text and never use an ellipsis. "
            "Use at most three bullets per slide and at most twelve words per bullet. "
            "Choose a meaningful editable visual_type and provide one to three very short visual_labels. "
            "Write 45 to 75 words of speaker_notes for every slide in warm, natural spoken English. "
            "The notes should sound like a thoughtful practitioner speaking to colleagues, with varied openings, "
            "contractions where natural, and a gentle transition to the next idea. Never say 'on this slide', "
            "'let's dive in', or 'as an AI'. Do not use bullets, stage directions, Markdown links, URLs, citations, "
            "or repeat the slide text verbatim. Preserve factual meaning and do not add facts absent from the source post."
        ),
        input=f"TOPIC: {topic}\n\nDESIGN BRIEF: {design_instructions}\n\nAPPROVED POST:\n{post}",
        text_format=SlideDeckPlan,
    )
    if not response.output_parsed:
        raise RuntimeError("OpenAI did not return a usable slide plan")
    slides = response.output_parsed.slides
    for index, slide in enumerate(slides, 1):
        slide.slide_number = index
        slide.title = slide.title.rstrip(" …")
        slide.content = [point.rstrip(" …") for point in slide.content[:3]]
        slide.visual_labels = [label.rstrip(" …") for label in slide.visual_labels[:3]]
        slide.speaker_notes = " ".join(slide.speaker_notes.split()).strip()
    return slides
