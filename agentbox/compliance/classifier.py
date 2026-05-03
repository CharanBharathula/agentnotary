"""
agentbox.compliance.classifier
==============================
Deterministic, auditable risk classifier for AI agents.

The classifier is a rule engine, NOT an LLM call. Every classification cites
the rule(s) that fired, so a compliance officer can re-derive the result.

Rules are ordered by severity. The first matching rule wins, but all firing
rules are reported for transparency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agentbox.manifest import AgentManifest


@dataclass
class RiskRule:
    code: str
    risk_class: str  # minimal | limited | high | unacceptable
    description: str


@dataclass
class FiredRule:
    rule: RiskRule
    matched: str  # the data that triggered the rule


@dataclass
class RiskAssessment:
    risk_class: str
    fired_rules: list = field(default_factory=list)
    declared_risk_class: Optional[str] = None
    summary: str = ""


# ── Rules ──────────────────────────────────────────────────────────────


# EU AI Act Article 5 — prohibited (unacceptable) systems
UNACCEPTABLE_RULES = [
    RiskRule("EU-AI-ACT-5.1.a", "unacceptable",
             "Subliminal techniques to materially distort behavior"),
    RiskRule("EU-AI-ACT-5.1.b", "unacceptable",
             "Exploits vulnerabilities of specific groups"),
    RiskRule("EU-AI-ACT-5.1.c", "unacceptable",
             "Social scoring by public authorities"),
    RiskRule("EU-AI-ACT-5.1.d", "unacceptable",
             "Real-time remote biometric identification in public spaces"),
]

# Annex III — high-risk system categories
HIGH_RISK_KEYWORDS = {
    "biometric": ["biometric", "facial_recognition", "fingerprint", "voice_id"],
    "critical_infrastructure": ["traffic_control", "power_grid", "water_supply"],
    "education": ["student_grading", "exam_scoring", "admissions"],
    "employment": ["resume_screen", "hiring", "candidate_ranking", "performance_review"],
    "essential_services": ["credit_score", "loan_decision", "insurance_pricing", "welfare"],
    "law_enforcement": ["crime_prediction", "evidence_review", "polygraph"],
    "migration": ["visa_review", "asylum_assessment", "border_control"],
    "justice": ["judicial_assistance", "case_law_review", "sentencing"],
    "healthcare": ["medical_diagnosis", "treatment_recommend", "prescribe", "clinical"],
    "payment": ["payment", "transfer_funds", "wire_transfer", "transact"],
}


def _matches_high_risk(text: str) -> Optional[tuple]:
    t = text.lower()
    for category, keywords in HIGH_RISK_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                return category, kw
    return None


# ── Classifier ─────────────────────────────────────────────────────────


def classify_risk(manifest: AgentManifest) -> RiskAssessment:
    """
    Run the deterministic classifier and return an auditable RiskAssessment.

    Inputs considered:
        - manifest.tools (names + types + endpoints)
        - manifest.compliance.affected_users
        - manifest.compliance.data_handling
        - manifest.compliance.intended_purpose (text scan)
    """
    fired: list[FiredRule] = []

    declared = None
    if manifest.compliance:
        declared = manifest.compliance.risk_class

    # ── Tier 1: unacceptable (prohibited) ─────────────────────────
    if manifest.compliance:
        purpose = (manifest.compliance.intended_purpose or "").lower()
        for rule in UNACCEPTABLE_RULES:
            for trigger in ["subliminal", "social scoring", "remote biometric",
                            "exploit vulnerab"]:
                if trigger in purpose:
                    fired.append(FiredRule(rule=rule, matched=trigger))

    if any(f.rule.risk_class == "unacceptable" for f in fired):
        return RiskAssessment(
            risk_class="unacceptable",
            fired_rules=fired,
            declared_risk_class=declared,
            summary=("This agent matches one or more prohibited use cases under "
                     "EU AI Act Article 5. It MUST NOT be deployed in the EU market."),
        )

    # ── Tier 2: high-risk (Annex III) ─────────────────────────────
    text_pool = []
    if manifest.compliance:
        text_pool.append(manifest.compliance.intended_purpose)
    for t in manifest.tools:
        text_pool.append(t.name)
        if t.endpoint:
            text_pool.append(t.endpoint)
    for kw in (manifest.tags or []):
        text_pool.append(kw)
    if manifest.compliance:
        text_pool.extend(manifest.compliance.data_handling.pii_categories)

    combined = " ".join(text_pool).lower()
    match = _matches_high_risk(combined)
    if match:
        category, keyword = match
        fired.append(FiredRule(
            rule=RiskRule(
                code=f"EU-AI-ACT-ANNEX-III-{category}",
                risk_class="high",
                description=f"Agent operates in Annex III high-risk domain: {category}",
            ),
            matched=f"keyword '{keyword}' in agent description/tools",
        ))

    # Vulnerable population access
    if manifest.compliance and manifest.compliance.affected_users in ("minors", "vulnerable_population"):
        fired.append(FiredRule(
            rule=RiskRule(
                code="EU-AI-ACT-VULNERABLE-USERS",
                risk_class="high",
                description="Affects minors or vulnerable populations",
            ),
            matched=manifest.compliance.affected_users,
        ))

    # Biometric processing
    if manifest.compliance and "biometric" in [c.lower() for c in
                                                 manifest.compliance.data_handling.pii_categories]:
        fired.append(FiredRule(
            rule=RiskRule(
                code="EU-AI-ACT-BIOMETRIC",
                risk_class="high",
                description="Processes biometric data",
            ),
            matched="biometric in pii_categories",
        ))

    if any(f.rule.risk_class == "high" for f in fired):
        return RiskAssessment(
            risk_class="high",
            fired_rules=fired,
            declared_risk_class=declared,
            summary=("Classified as HIGH RISK under EU AI Act Annex III. Conformity "
                     "assessment, registration in the EU database, and post-market "
                     "monitoring obligations apply."),
        )

    # ── Tier 3: limited risk (transparency obligations) ───────────
    is_external = (manifest.compliance and
                   manifest.compliance.affected_users == "external_consumers")
    has_user_facing_chat = any("chat" in (t.name or "").lower() or "support" in (t.name or "").lower()
                                for t in manifest.tools) or is_external

    if is_external or has_user_facing_chat:
        fired.append(FiredRule(
            rule=RiskRule(
                code="EU-AI-ACT-TRANSPARENCY",
                risk_class="limited",
                description=("Consumer-facing AI system. Article 52 transparency "
                             "obligations apply (must disclose AI nature)."),
            ),
            matched="affected_users=external_consumers" if is_external else "user-facing tool",
        ))
        return RiskAssessment(
            risk_class="limited",
            fired_rules=fired,
            declared_risk_class=declared,
            summary=("Classified as LIMITED RISK. Transparency obligations: agent must "
                     "disclose its AI nature to users."),
        )

    # ── Tier 4: minimal risk (default) ────────────────────────────
    fired.append(FiredRule(
        rule=RiskRule(
            code="EU-AI-ACT-MINIMAL",
            risk_class="minimal",
            description="No high-risk indicators detected; internal use only",
        ),
        matched="no triggering rules fired",
    ))
    return RiskAssessment(
        risk_class="minimal",
        fired_rules=fired,
        declared_risk_class=declared,
        summary=("Classified as MINIMAL RISK. No specific obligations under the EU AI Act, "
                 "though voluntary code-of-conduct adherence is encouraged."),
    )
