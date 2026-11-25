"""
Dream / super-dream offer tiers. The ONE place that turns a package into a
tier and decides whether a placed student may apply to a role.
"""
from decimal import Decimal

TIER_RANK = {"regular": 1, "dream": 2, "super_dream": 3}
TIER_LABEL = {"regular": "Regular", "dream": "Dream", "super_dream": "Super dream"}


def current_policy():
    from .models import PlacementPolicy
    return PlacementPolicy.current()


def tier_for(package_lpa, policy=None):
    """'regular' | 'dream' | 'super_dream', or None when tiers are off."""
    policy = policy or current_policy()
    if not policy.tiers_enabled:
        return None
    pkg = Decimal(str(package_lpa)) if package_lpa is not None else None
    if pkg is not None and policy.super_dream_min_lpa is not None and pkg >= policy.super_dream_min_lpa:
        return "super_dream"
    if pkg is not None and policy.dream_min_lpa is not None and pkg >= policy.dream_min_lpa:
        return "dream"
    return "regular"


def best_accepted_offer(student):
    from .models import Offer
    return (
        Offer.objects
        .filter(application__student=student, status="accepted")
        .select_related("application__job_role__drive__company")
        .order_by("-package_lpa")
        .first()
    )


_UNSET = object()


def tier_check(student, job_role, policy=None, best=_UNSET):
    """
    None when tiers are off. Otherwise a dict for eligibility.py:
    {required, actual, passed, reason}.
    """
    policy = policy or current_policy()
    if not policy.tiers_enabled:
        return None

    role_tier = tier_for(job_role.package_lpa, policy)
    if best is _UNSET:
        best = best_accepted_offer(student)
    if best is None:
        return {
            "required": f"{TIER_LABEL[role_tier]} role",
            "actual": "No accepted offer",
            "passed": True,
            "reason": "",
        }

    held = tier_for(best.package_lpa, policy)
    company = best.application.job_role.drive.company.name
    passed = TIER_RANK[role_tier] > TIER_RANK[held]
    higher = [TIER_LABEL[t] for t, r in TIER_RANK.items() if r > TIER_RANK[held]]
    if passed:
        reason = ""
    elif higher:
        reason = (
            f"You hold a {TIER_LABEL[held]} offer ({best.package_lpa} LPA at {company}). "
            f"Only {' / '.join(higher)} roles are open to you."
        )
    else:
        reason = (
            f"You hold a Super dream offer ({best.package_lpa} LPA at {company}), "
            "so your placement is complete."
        )
    return {
        "required": f"{TIER_LABEL[role_tier]} role, above your current tier",
        "actual": f"{TIER_LABEL[held]} offer ({best.package_lpa} LPA, {company})",
        "passed": passed,
        "reason": reason,
    }
