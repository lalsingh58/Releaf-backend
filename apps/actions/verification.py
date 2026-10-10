"""
Proof verification.

``verify_proof_image`` is the single extension point for checking that a
photo really shows someone planting / watering. The default implementation is
a PLACEHOLDER: basic file validation already happened in the serializer, so it
only decides between "approve immediately" and "leave for manual review"
based on ``settings.PROOF_AUTO_APPROVE``.

To plug in a real verifier, write a function with the same signature and point
``PROOF_VERIFIER`` (env var / setting) at it, e.g.
``PROOF_VERIFIER=apps.actions.cloud_vision.verify_proof_image``.
"""
from dataclasses import dataclass
from typing import Optional

from django.conf import settings

from .models import Proof, ProofStatus


@dataclass(frozen=True)
class VerificationResult:
    status: str  # one of ProofStatus values
    note: str = ""
    confidence: Optional[float] = None  # 0.0 - 1.0, when an AI model provides one


def verify_proof_image(proof: Proof) -> VerificationResult:
    """
    PLACEHOLDER for AI image verification (e.g. Google Cloud Vision).

    Sketch of a Google Cloud Vision implementation (``pip install google-cloud-vision``,
    set GOOGLE_APPLICATION_CREDENTIALS)::

        from google.cloud import vision

        EXPECTED_LABELS = {"plant", "tree", "sapling", "soil", "garden", "watering can", "leaf"}

        def verify_proof_image(proof):
            client = vision.ImageAnnotatorClient()
            with proof.image.open("rb") as fh:
                response = client.label_detection(image=vision.Image(content=fh.read()))
            labels = {l.description.lower(): l.score for l in response.label_annotations}
            matches = [score for name, score in labels.items() if name in EXPECTED_LABELS]
            if matches and max(matches) >= 0.7:
                return VerificationResult(ProofStatus.APPROVED, "Plant detected", max(matches))
            if not matches:
                return VerificationResult(ProofStatus.REJECTED, "No plant or tree detected", 0.0)
            return VerificationResult(ProofStatus.PENDING, "Low confidence, needs review", max(matches))

    Return ``PENDING`` whenever the model is unsure so a human can decide in the admin.
    """
    if settings.PROOF_AUTO_APPROVE:
        return VerificationResult(
            status=ProofStatus.APPROVED,
            note="Auto-approved: passed basic validation (AI verification not enabled yet).",
        )
    return VerificationResult(
        status=ProofStatus.PENDING,
        note="Awaiting manual review.",
    )
