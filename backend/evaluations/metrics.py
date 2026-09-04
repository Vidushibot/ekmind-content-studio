from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


TOKEN = re.compile(r"[a-z0-9]+", re.I)
NUMBER = re.compile(r"(?<!\w)\d+(?:\.\d+)?%?")
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
URL = re.compile(r"https?://\S+|\[[^]]+\]\([^)]+\)")
SECRET = re.compile(r"\b(sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|refresh_token\s*[=:])", re.I)
ATTRIBUTION = re.compile(r"\b(according to|research|study|survey|report(?:ed)?|data|found|shows?)\b", re.I)
CAPABILITY = re.compile(r"\b(supports?|provides?|offers?|released?|requires?|includes?|allows?|integrates?|features?|enables?)\b", re.I)
RECOMMENDATION = re.compile(r"\b(should|consider|recommend|try|start by|focus on|need to|must)\b", re.I)
CTA = re.compile(r"^(explore|learn|read|discover|visit|click|download|contact|watch|see)\b", re.I)
NEGATION = re.compile(r"\b(no|not|never|without|doesn't|does not|cannot|can't|isn't|aren't)\b", re.I)
CERTAIN_MODAL = re.compile(r"\b(will|always|guarantees?|ensures?|proves?)\b", re.I)
UNCERTAIN_MODAL = re.compile(r"\b(may|might|could|can|suggests?|potentially)\b", re.I)
STOPWORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in", "is", "it", "of", "on", "or", "that", "the", "their", "this", "to", "with", "your"}


@dataclass(frozen=True)
class ClaimAssessment:
    claim: str
    classification: str
    evidence_ids: tuple[str, ...]
    score: float
    reason: str
    sentence_type: str = "FACTUAL_CLAIM"
    material: bool = False
    confidence: float = 0.0
    best_passage: str = ""
    source_title: str = ""
    source_url: str = ""
    signals: tuple[str, ...] = ()


def evidence_coverage(expected_claim_ids: set[str], supported_claim_ids: set[str]) -> float | None:
    if not expected_claim_ids:
        return None
    return round(len(expected_claim_ids & supported_claim_ids) / len(expected_claim_ids), 3)


def classify_sentence(sentence: str) -> str:
    clean = URL.sub("", sentence).strip(" -*#")
    if not clean or CTA.search(clean):
        return "CALL_TO_ACTION"
    if sentence.rstrip().endswith("?"):
        return "QUESTION"
    if re.search(r"\b(I|we)\s+(believe|think|feel|learned|implemented|experienced)\b", clean, re.I):
        return "PERSONAL_EXPERIENCE"
    if RECOMMENDATION.search(clean) and not (NUMBER.search(clean) or ATTRIBUTION.search(clean)):
        return "RECOMMENDATION"
    if NUMBER.search(clean) or ATTRIBUTION.search(clean) or CAPABILITY.search(clean):
        return "FACTUAL_CLAIM"
    return "OPINION"


def extract_factual_claims(text: str) -> list[str]:
    sentences = [part.strip() for part in SENTENCE.split(text) if part.strip()]
    return [sentence for sentence in sentences if classify_sentence(sentence) == "FACTUAL_CLAIM"]


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN.findall(URL.sub("", text)) if token.casefold() not in STOPWORDS and len(token) > 1}


def _passages(text: str) -> list[str]:
    cleaned = " ".join(str(text).replace("�", "'").split())
    sentences = [part.strip() for part in SENTENCE.split(cleaned) if len(part.strip()) >= 15]
    if not sentences:
        return [cleaned] if cleaned else []
    passages = list(sentences)
    passages.extend(" ".join(sentences[index:index + 2]) for index in range(len(sentences) - 1))
    passages.extend(" ".join(sentences[index:index + 3]) for index in range(len(sentences) - 2))
    return passages


def _similarity(claim: str, passage: str) -> float:
    claim_tokens, passage_tokens = _tokens(claim), _tokens(passage)
    if not claim_tokens or not passage_tokens:
        return 0.0
    coverage = len(claim_tokens & passage_tokens) / len(claim_tokens)
    jaccard = len(claim_tokens & passage_tokens) / len(claim_tokens | passage_tokens)
    sequence = SequenceMatcher(None, URL.sub("", claim).casefold(), passage.casefold()).ratio()
    return round(coverage * 0.6 + jaccard * 0.25 + sequence * 0.15, 4)


def assess_faithfulness(claims: list[str], evidence: list[dict[str, object]]) -> list[ClaimAssessment]:
    results: list[ClaimAssessment] = []
    for claim in claims:
        sentence_type = classify_sentence(claim)
        if sentence_type != "FACTUAL_CLAIM":
            results.append(ClaimAssessment(claim, "NOT_APPLICABLE", (), 0.0, "The sentence is not a factual claim.", sentence_type=sentence_type, confidence=1.0))
            continue
        best_score, best_item, best_passage = 0.0, None, ""
        for item in evidence:
            for passage in _passages(str(item.get("text") or item.get("claim") or "")):
                score = _similarity(claim, passage)
                if score > best_score:
                    best_score, best_item, best_passage = score, item, passage
        signals: list[str] = []
        claim_numbers, passage_numbers = set(NUMBER.findall(claim)), set(NUMBER.findall(best_passage))
        number_conflict = bool(claim_numbers and not claim_numbers <= passage_numbers)
        negation_conflict = bool(NEGATION.search(claim)) != bool(NEGATION.search(best_passage)) and best_score >= 0.3
        modality_overstatement = bool(CERTAIN_MODAL.search(claim) and UNCERTAIN_MODAL.search(best_passage))
        if number_conflict: signals.append("NUMBER_MISMATCH")
        if negation_conflict: signals.append("NEGATION_MISMATCH")
        if modality_overstatement: signals.append("MODALITY_OVERSTATEMENT")
        if number_conflict or negation_conflict:
            classification, reason, confidence = "CONTRADICTED", "The best evidence conflicts with a number or negation in the claim.", 0.95
        elif best_score >= 0.44 and not modality_overstatement:
            classification, reason, confidence = "SUPPORTED", "A focused evidence passage supports the claim's material wording.", min(0.98, 0.55 + best_score * 0.55)
        elif best_score >= 0.30:
            classification, reason, confidence = "PARTIALLY_SUPPORTED", "Related evidence supports part, but not all, of the claim.", min(0.85, 0.45 + best_score * 0.5)
        elif best_score >= 0.20:
            classification, reason, confidence = "NEEDS_HUMAN_REVIEW", "Some evidence overlaps, but automated support is inconclusive.", 0.5
        else:
            classification, reason, confidence = "UNSUPPORTED", "No focused passage sufficiently supports the claim.", min(0.95, 0.7 + (0.20 - best_score))
        evidence_id = str(best_item.get("evidence_id", "")) if best_item else ""
        results.append(ClaimAssessment(claim, classification, (evidence_id,) if evidence_id else (), round(best_score, 3), reason, sentence_type, is_material_claim(claim), round(confidence, 3), best_passage[:700], str(best_item.get("source_title", "")) if best_item else "", str(best_item.get("source_url", "")) if best_item else "", tuple(signals)))
    return results


def faithfulness_score(assessments: list[ClaimAssessment] | list[dict[str, object]]) -> float | None:
    weights = {"SUPPORTED": 1.0, "PARTIALLY_SUPPORTED": 0.5, "UNSUPPORTED": 0.0, "CONTRADICTED": 0.0}
    classifications = [str((item.get("effective_classification") or item.get("classification"))) if isinstance(item, dict) else item.classification for item in assessments]
    evaluated = [classification for classification in classifications if classification in weights]
    return round(sum(weights[classification] for classification in evaluated) / len(evaluated) * 10, 2) if evaluated else None


def contains_secret(text: str) -> bool:
    return bool(SECRET.search(text))


def is_material_claim(claim: str) -> bool:
    return bool(NUMBER.search(claim) or ATTRIBUTION.search(claim) or CAPABILITY.search(claim))
