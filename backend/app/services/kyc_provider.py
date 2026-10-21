"""
KYC provider boundary (SDS 3.3: verification is done by a third-party provider,
not in-house). Everything else in the app talks to `KycProvider`, so replacing the
mock with a real vendor later means writing one new class here, nothing else.

The mock is deterministic so every outcome can be demonstrated on demand:

  CNIC check   last digit 0  -> failed
               last digit 9  -> pending on first submission, verified when the
                                same CNIC is submitted again (simulates a manual
                                review finishing)
               anything else -> verified
  Liveness     image text starting with "FAIL" -> failed, anything else -> verified
  OTP          the fixed code in settings.MOCK_OTP_CODE
"""

import hmac
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings

VERIFIED = "verified"
PENDING = "pending"
FAILED = "failed"


@dataclass(frozen=True)
class CheckResult:
    status: str  # verified | pending | failed
    reason: str | None = None


class KycProvider(Protocol):
    def check_cnic(self, cnic: str, previously_submitted: bool) -> CheckResult: ...

    def check_liveness(self, image: str) -> CheckResult: ...

    def send_otp(self, phone: str) -> None: ...

    def check_otp(self, phone: str, code: str) -> bool: ...


class MockKycProvider:
    def check_cnic(self, cnic: str, previously_submitted: bool) -> CheckResult:
        last = cnic[-1]
        if last == "0":
            return CheckResult(FAILED, "CNIC could not be validated.")
        if last == "9":
            return CheckResult(VERIFIED) if previously_submitted else CheckResult(PENDING, "Under review.")
        return CheckResult(VERIFIED)

    def check_liveness(self, image: str) -> CheckResult:
        if image.startswith("FAIL"):
            return CheckResult(FAILED, "Liveness check failed. Please retake the photo.")
        return CheckResult(VERIFIED)

    def send_otp(self, phone: str) -> None:
        return None  # nothing is actually sent

    def check_otp(self, phone: str, code: str) -> bool:
        return hmac.compare_digest(code.encode(), get_settings().MOCK_OTP_CODE.encode())


def get_kyc_provider() -> KycProvider:
    return MockKycProvider()
