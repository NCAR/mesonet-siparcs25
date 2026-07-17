"""
mrt_calculator.py

Mean Radiant Temperature (MRT / Tmr) from a globe thermometer, per ISO 7726 (Eq. 6):

    Tmr = [ (Tg + 273.15)^4 + (hcg / (eps_g * sigma)) * (Tg - Ta) ]^(1/4) - 273.15

where hcg (convective heat transfer coefficient, W/m2K) is:

    Natural convection:  hcg = 1.4 * (|Ta - Tg| / D)^0.25
    Forced convection:   hcg = 6.3 * va^0.6 / D^0.4

hc,g is taken as the MAX of the two (self-selects the dominant regime and
avoids a discontinuity at the natural/forced switch point).

Inputs:
    Tg   - globe temperature (deg C)
    Ta   - air temperature (deg C)
    va   - air velocity at globe height (m/s)
    D    - globe diameter (m). Default here is 0.038 m (3.8 cm), matching
           the OpenIoTwx device's ping-pong-ball-style globe (older ITTF
           standard; current balls are 40mm). Standard ISO 7726 globes are
           0.15 m -- pass D=0.15 explicitly if you're working with a
           standard globe instead.
    eps_g - globe emissivity (dimensionless). ~0.95 for a matte black globe.

Note: smaller globes have a substantially larger hc,g than a standard 150mm
globe at the same Ta/Tg/v (hc,g scales as D^-0.25 to D^-0.4), so getting
va right (measured at globe height/position, not from a remote/10m sensor)
matters more for small fast-response globes than for standard ones. Small
globes should ideally be calibrated against a radiometer-based MRT reference.
"""

from __future__ import annotations

SIGMA = 5.670374419e-8  # Stefan-Boltzmann constant, W/m2K4

# OpenIoTwx globe defaults -- update here if the physical globe changes
DEFAULT_GLOBE_DIAMETER_M = 0.038  # 3.8 cm (older ping-pong ball standard)
DEFAULT_GLOBE_EMISSIVITY = 0.95


def hcg_natural(Ta: float, Tg: float, D: float) -> float:
    """Natural convection heat transfer coefficient, W/m2K."""
    return 1.4 * (abs(Ta - Tg) / D) ** 0.25


def hcg_forced(va: float, D: float) -> float:
    """Forced convection heat transfer coefficient, W/m2K."""
    return 6.3 * (va ** 0.6) / (D ** 0.4)


def calculate_mrt(
    Tg: float,
    Ta: float,
    va: float,
    D: float = DEFAULT_GLOBE_DIAMETER_M,
    eps_g: float = DEFAULT_GLOBE_EMISSIVITY,
) -> dict:
    """
    Compute Mean Radiant Temperature from globe thermometer data (ISO 7726).

    Args:
        Tg: globe temperature, deg C
        Ta: air temperature, deg C
        va: air velocity at globe height, m/s
        D: globe diameter, m (default 0.038 m -- OpenIoTwx 3.8 cm globe)
        eps_g: globe emissivity (default 0.95)

    Returns:
        dict with mrt_c, mrt_k, hcg_used, regime ("natural" or "forced"),
        and both candidate hcg values for diagnostics.
    """
    if D <= 0:
        raise ValueError("Globe diameter D must be > 0")
    if eps_g <= 0 or eps_g > 1:
        raise ValueError("eps_g must be in (0, 1]")
    if va < 0:
        raise ValueError("va must be >= 0")

    h_nat = hcg_natural(Ta, Tg, D)
    h_forced = hcg_forced(va, D) if va > 0 else 0.0

    if h_forced > h_nat:
        hcg = h_forced
        regime = "forced"
    else:
        hcg = h_nat
        regime = "natural"

    Tg_k = Tg + 273.15
    inner = Tg_k ** 4 + (hcg / (eps_g * SIGMA)) * (Tg - Ta)

    if inner < 0:
        # Guards against pathological inputs (e.g. huge hcg with Tg << Ta)
        raise ValueError(
            f"Computed negative value under 4th root (inner={inner:.3f}). "
            "Check Tg/Ta/va/D inputs."
        )

    mrt_k = inner ** 0.25
    mrt_c = mrt_k - 273.15

    return {
        "mrt_c": mrt_c,
        "mrt_k": mrt_k,
        "hcg_used": hcg,
        "regime": regime,
        "hcg_natural": h_nat,
        "hcg_forced": h_forced,
        "D": D,
        "eps_g": eps_g,
    }


if __name__ == "__main__":
    # Quick sanity check using the OpenIoTwx 3.8 cm globe defaults
    result = calculate_mrt(Tg=45.0, Ta=32.0, va=1.5)
    print(result)