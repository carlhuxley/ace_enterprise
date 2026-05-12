"""Bayesian success-rate estimation using the Beta-Binomial model.

Bead: ace_enterprise-2uq

Model
-----
Prior:     Beta(alpha_prior, beta_prior)   default = Beta(1, 1) = uniform
Posterior: Beta(alpha_prior + successes, beta_prior + failures)
CI:        scipy.stats.beta.interval(confidence_level, alpha_post, beta_post)

An estimate is flagged as INSUFFICIENT_DATA when the credible-interval width
exceeds INSUFFICIENT_DATA_THRESHOLD (default 0.30), meaning we are uncertain
enough that routing decisions should be treated with caution.
"""

from __future__ import annotations

from dataclasses import dataclass

from scipy.stats import beta as beta_dist

INSUFFICIENT_DATA_THRESHOLD = 0.30  # CI width above which data is considered sparse


@dataclass
class BayesianEstimate:
    """Posterior summary of a Beta-Binomial success-rate model."""

    mean: float             # posterior mean = alpha_post / (alpha_post + beta_post)
    ci_lower: float         # lower bound of credible interval
    ci_upper: float         # upper bound of credible interval
    ci_width: float         # ci_upper - ci_lower
    is_insufficient_data: bool  # True when ci_width > INSUFFICIENT_DATA_THRESHOLD
    alpha_posterior: float
    beta_posterior: float
    confidence_level: float = 0.95


def estimate_success_rate(
    successes: int,
    failures: int,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
    confidence_level: float = 0.95,
) -> BayesianEstimate:
    """Compute a Bayesian estimate of the true success rate.

    Args:
        successes:        Number of observed successes.
        failures:         Number of observed failures.
        prior_alpha:      Alpha parameter of the Beta prior (default 1 = uniform).
        prior_beta:       Beta  parameter of the Beta prior (default 1 = uniform).
        confidence_level: Width of the credible interval (default 0.95).

    Returns:
        BayesianEstimate with posterior mean, CI bounds, and data-sufficiency flag.
    """
    alpha_post = prior_alpha + successes
    beta_post = prior_beta + failures

    mean = alpha_post / (alpha_post + beta_post)
    ci_lower, ci_upper = beta_dist.interval(confidence_level, alpha_post, beta_post)
    ci_width = float(ci_upper) - float(ci_lower)

    return BayesianEstimate(
        mean=float(mean),
        ci_lower=float(ci_lower),
        ci_upper=float(ci_upper),
        ci_width=ci_width,
        is_insufficient_data=ci_width > INSUFFICIENT_DATA_THRESHOLD,
        alpha_posterior=float(alpha_post),
        beta_posterior=float(beta_post),
        confidence_level=confidence_level,
    )
