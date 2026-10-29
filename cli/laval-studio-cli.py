#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Laval Studio — versión de línea de comandos
# Copyright (c) 2026 Marco Contini — Licencia MIT
# https://github.com/marcontini/laval-studio
"""
laval-studio-cli.py
===================
Diseño interno de tobera para motor cohete de propelente sólido.

Dadas las características del propelente, la presión de cámara y las LONGITUDES
de los tramos convergente y divergente, calcula:

  * el área y diámetro de garganta (desde la presión, o desde el área de
    quemado del grano por equilibrio de Saint-Robert),
  * la relación de expansión óptima y el diámetro de salida,
  * LOS ÁNGULOS de semicono convergente y divergente,
  * prestaciones: c*, C_F, empuje, Isp, gasto másico,
  * el contorno 2D y la distribución axial de Mach, presión y temperatura.

NOTA IMPORTANTE SOBRE EL PLANTEAMIENTO
--------------------------------------
Dada la longitud, el ángulo NO es un grado de libertad: queda determinado por
la longitud, el radio de garganta y el radio de salida. Por eso aquí el ángulo
es una SALIDA, no una entrada. Si el ángulo que sale no gusta, lo que hay que
cambiar es la longitud (o la relación de expansión), no el ángulo.

Hipótesis del modelo: flujo isentrópico, cuasi-1D, gas ideal de composición
congelada, equilibrio en la cámara. Es el modelo estándar de diseño preliminar
(Sutton & Biblarz). No modela capa límite, transitorio de ignición, erosión de
garganta ni flujo bifásico.

Dependencias: numpy, matplotlib.

Uso rápido:
    python laval-studio-cli.py                          # ejemplo APCP clase M
    python laval-studio-cli.py --preset knsu --pc 35
    python laval-studio-cli.py --pc 50 --dt 10.6 --l-div 32.5 --contour bell
    python laval-studio-cli.py --ab 48000 --pc 50       # garganta desde el grano
    python laval-studio-cli.py --help
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field

import numpy as np

# =====================================================================
# Constantes
# =====================================================================
R_U = 8.31446261815324      # constante universal de los gases [J/(mol K)]
G0 = 9.80665                # gravedad estándar [m/s^2]
P_ATM = 101325.0            # presión atmosférica a nivel del mar [Pa]

# Paleta (validada para visión con deficiencia cromática en fondo claro)
C_WALL = "#2F3B46"
C_GAS = "#DCE8F0"
C_AXIS = "#8A949C"
C_MACH = "#0E5C8A"
C_PRES = "#B4531A"
C_NOTE = "#5A6672"


# =====================================================================
# Propelente
# =====================================================================
@dataclass
class Propellant:
    """Propiedades termoquímicas y balísticas de un propelente sólido.

    `a` y `n` son los coeficientes de la ley de Saint-Robert  r = a * Pc^n,
    con `a` ya convertido a unidades SI (m/s por Pa^n). Usar los
    constructores `from_bar` / `from_mpa` para no equivocarse.
    """
    name: str
    gamma: float            # razón de calores específicos [-]
    M: float                # masa molar de los productos [kg/mol]
    T_c: float              # temperatura de llama adiabática [K]
    rho: float              # densidad del propelente sólido [kg/m^3]
    a: float                # coef. de velocidad de quemado [m/s / Pa^n]
    n: float                # exponente de presión [-]
    eta_cstar: float = 0.95  # eficiencia de c* (pérdidas reales de cámara)
    source: str = ""

    # ---------------- constructores con unidades prácticas -------------
    @classmethod
    def from_bar(cls, a_mm_s_bar: float, n: float, **kw) -> "Propellant":
        """`a` dado en mm/s cuando la presión se expresa en bar."""
        return cls(a=1e-3 * a_mm_s_bar * (1e-5) ** n, n=n, **kw)

    @classmethod
    def from_mpa(cls, a_mm_s_mpa: float, n: float, **kw) -> "Propellant":
        """`a` dado en mm/s cuando la presión se expresa en MPa."""
        return cls(a=1e-3 * a_mm_s_mpa * (1e-6) ** n, n=n, **kw)

    # ---------------- propiedades derivadas ----------------------------
    @property
    def R(self) -> float:
        """Constante específica del gas [J/(kg K)]."""
        return R_U / self.M

    @property
    def Gamma(self) -> float:
        """Función de Vandenkerckhove."""
        g = self.gamma
        return math.sqrt(g) * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))

    @property
    def c_star_ideal(self) -> float:
        """Velocidad característica ideal [m/s]."""
        return math.sqrt(self.R * self.T_c) / self.Gamma

    @property
    def c_star(self) -> float:
        """Velocidad característica corregida por eficiencia [m/s]."""
        return self.eta_cstar * self.c_star_ideal

    def burn_rate(self, pc: float) -> float:
        """Velocidad de quemado [m/s] a presión de cámara `pc` [Pa]."""
        return self.a * pc ** self.n


# ---------------------------------------------------------------------
# Presets. VERIFICAR contra los datos del propio lote antes de fabricar.
# ---------------------------------------------------------------------
PRESETS = {
    # Composición AP/HTPB aluminizada. Datos de Godil & Kamran (2017),
    # Aircraft Eng. & Aerospace Tech. 89(6), Tabla I.
    "apcp": lambda: Propellant.from_bar(
        a_mm_s_bar=1.559, n=0.47,
        name="APCP AP/HTPB aluminizado",
        gamma=1.20, M=27.71e-3, T_c=3500.0, rho=1760.0,
        source="Godil & Kamran (2017), AEAT 89(6), Tabla I",
    ),
    # Candy KNO3/sacarosa 65/35. Valores tipo Nakka: APROXIMADOS, varían
    # mucho con el proceso de fabricación y la humedad. Caracterizar el lote.
    "knsu": lambda: Propellant.from_mpa(
        a_mm_s_mpa=8.26, n=0.319,
        name="KNSU candy KNO3/sacarosa 65/35",
        gamma=1.133, M=41.98e-3, T_c=1720.0, rho=1889.0,
        source="Valores tipo Nakka - APROXIMADOS, caracterizar el lote propio",
    ),
}


# =====================================================================
# Relaciones isentrópicas
# =====================================================================
def _bisect(f, lo: float, hi: float, tol: float = 1e-13, itmax: int = 300) -> float:
    """Bisección robusta. Se usa en lugar de scipy para no añadir dependencias."""
    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0.0:
        raise ValueError(
            f"No hay cambio de signo en [{lo}, {hi}]: f(lo)={flo:.4g}, f(hi)={fhi:.4g}"
        )
    for _ in range(itmax):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if fm == 0.0 or (hi - lo) < tol:
            return mid
        if flo * fm < 0.0:
            hi = mid
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


def area_ratio_from_mach(M: float, gamma: float) -> float:
    """A/A* en función del número de Mach."""
    g = gamma
    return (1.0 / M) * ((2.0 / (g + 1.0)) * (1.0 + 0.5 * (g - 1.0) * M * M)) ** (
        (g + 1.0) / (2.0 * (g - 1.0))
    )


def mach_from_area_ratio(eps: float, gamma: float, supersonic: bool = True) -> float:
    """Mach a partir de A/A*. `supersonic` elige la rama de la solución."""
    if eps <= 1.0:
        return 1.0
    f = lambda M: area_ratio_from_mach(M, gamma) - eps
    return _bisect(f, 1.0 + 1e-12, 100.0) if supersonic else _bisect(f, 1e-6, 1.0)


def mach_from_pressure_ratio(pc_over_pe: float, gamma: float) -> float:
    """Mach de salida a partir de la relación de presiones Pc/Pe."""
    g = gamma
    return math.sqrt(2.0 / (g - 1.0) * (pc_over_pe ** ((g - 1.0) / g) - 1.0))


def pressure_ratio_from_mach(M: float, gamma: float) -> float:
    """P/Pc en función del número de Mach."""
    return (1.0 + 0.5 * (gamma - 1.0) * M * M) ** (-gamma / (gamma - 1.0))


def temperature_ratio_from_mach(M: float, gamma: float) -> float:
    """T/Tc en función del número de Mach."""
    return 1.0 / (1.0 + 0.5 * (gamma - 1.0) * M * M)


def cf_momentum(pc: float, pe: float, gamma: float) -> float:
    """Término de cantidad de movimiento del coeficiente de empuje."""
    g = gamma
    Gam = math.sqrt(g) * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))
    return Gam * math.sqrt(2.0 * g / (g - 1.0) * (1.0 - (pe / pc) ** ((g - 1.0) / g)))


# =====================================================================
# Ángulos de tobera acampanada (Rao / TOP)
# =====================================================================
# Tabla digitalizada del gráfico clásico de Rao para tobera parabólica
# optimizada en empuje. Interpolación lineal en log(eps) y en % de longitud.
# Aviso: la fila del 60 % presenta una no-monotonía en eps=50 (35.0 entre 37.1
# y 40.0) que es un artefacto de digitalización de la fuente. El 80 % es el
# valor estándar de diseño y es la fila recomendada.
_RAO_EPS = np.array([4, 5, 10, 20, 30, 40, 50, 100], dtype=float)
_RAO_PCT = np.array([60.0, 80.0, 90.0])
_RAO_TN = np.array([
    [26.5, 28.0, 32.0, 35.0, 36.2, 37.1, 35.0, 40.0],   # 60 %
    [21.5, 23.0, 26.3, 28.8, 30.0, 31.0, 31.5, 33.5],   # 80 %
    [20.0, 21.0, 24.0, 27.0, 28.5, 29.5, 30.2, 32.0],   # 90 %
])
_RAO_TE = np.array([
    [20.5, 20.5, 16.0, 14.5, 14.0, 13.5, 13.0, 11.2],   # 60 %
    [14.0, 13.0, 11.0, 9.0, 8.5, 8.0, 7.5, 7.0],        # 80 %
    [11.5, 10.5, 8.0, 7.0, 6.5, 6.0, 6.0, 6.0],         # 90 %
])


def rao_angles(eps: float, pct: float) -> tuple[float, float, list[str]]:
    """Ángulos inicial y de salida de la parábola [grados], con avisos."""
    warn: list[str] = []
    if not (_RAO_EPS[0] <= eps <= _RAO_EPS[-1]):
        warn.append(
            f"eps={eps:.2f} fuera de la tabla de Rao [4, 100]: ángulos extrapolados."
        )
    if not (_RAO_PCT[0] <= pct <= _RAO_PCT[-1]):
        warn.append(
            f"Campana al {pct:.0f} % fuera de la tabla [60, 90]: ángulos extrapolados."
        )
    le = math.log(min(max(eps, 1.01), 500.0))
    rows_tn = [np.interp(le, np.log(_RAO_EPS), _RAO_TN[i]) for i in range(3)]
    rows_te = [np.interp(le, np.log(_RAO_EPS), _RAO_TE[i]) for i in range(3)]
    tn = float(np.interp(pct, _RAO_PCT, rows_tn))
    te = float(np.interp(pct, _RAO_PCT, rows_te))
    return tn, te, warn


# =====================================================================
# Geometría
# =====================================================================
def solve_cone_angle(r_t: float, r_end: float, length: float, r_arc: float) -> float:
    """Semiángulo del tramo recto [rad] que, partiendo de un arco de garganta de
    radio `r_arc`, alcanza exactamente `r_end` a la distancia axial `length`.

    Resuelve:  r_end = r_t + r_arc*(1 - cos a) + (length - r_arc*sin a)*tan a

    Con r_arc = 0 se reduce al cono ideal  a = atan((r_end - r_t)/length),
    que es la relación directa entre longitud y ángulo.
    """
    if r_end <= r_t:
        raise ValueError("El radio final debe ser mayor que el de garganta.")

    def resid(a: float) -> float:
        return (
            r_t + r_arc * (1.0 - math.cos(a)) + (length - r_arc * math.sin(a)) * math.tan(a)
        ) - r_end

    return _bisect(resid, math.radians(0.05), math.radians(75.0))


def contour_conical(r_t, r_e, r_c, l_div, l_conv, k_up=1.5, k_dn=0.5, npts=320):
    """Contorno de tobera cónica con arcos de acuerdo en la garganta.

    k_up, k_dn: radios de acuerdo aguas arriba y abajo, en múltiplos de r_t.
    Devuelve (x, y, alpha_rad, beta_rad).
    """
    r_up, r_dn = k_up * r_t, k_dn * r_t
    beta = solve_cone_angle(r_t, r_c, l_conv, r_up)
    alpha = solve_cone_angle(r_t, r_e, l_div, r_dn)

    # --- convergente: recta desde la cámara + arco hasta la garganta ---
    x_tan_up = -r_up * math.sin(beta)
    y_tan_up = r_t + r_up * (1.0 - math.cos(beta))
    x_line_c = np.linspace(-l_conv, x_tan_up, npts // 4)
    y_line_c = r_c - (x_line_c + l_conv) * math.tan(beta)
    th = np.linspace(-math.pi / 2 - beta, -math.pi / 2, npts // 4)
    x_arc_c = r_up * np.cos(th)
    y_arc_c = r_up * np.sin(th) + r_up + r_t

    # --- divergente: arco desde la garganta + recta hasta la salida ---
    th = np.linspace(-math.pi / 2, alpha - math.pi / 2, npts // 4)
    x_arc_d = r_dn * np.cos(th)
    y_arc_d = r_dn * np.sin(th) + r_dn + r_t
    x_tan_dn = r_dn * math.sin(alpha)
    y_tan_dn = r_t + r_dn * (1.0 - math.cos(alpha))
    x_line_d = np.linspace(x_tan_dn, l_div, npts // 4)
    y_line_d = y_tan_dn + (x_line_d - x_tan_dn) * math.tan(alpha)

    x = np.concatenate([x_line_c, x_arc_c, x_arc_d, x_line_d])
    y = np.concatenate([y_line_c, y_arc_c, y_arc_d, y_line_d])
    return x, y, alpha, beta


def contour_bell(r_t, r_e, r_c, l_div, l_conv, theta_n, theta_e, npts=320):
    """Contorno TOP (parabólico optimizado en empuje), construcción de Rao:
    arco de entrada de 1.5 r_t, arco de salida de 0.382 r_t y Bezier cuadrática.
    `theta_n`, `theta_e` en radianes. Devuelve (x, y, alpha_rad, beta_rad).
    """
    r_up = 1.5 * r_t
    beta = solve_cone_angle(r_t, r_c, l_conv, r_up)

    # convergente idéntico al cónico
    x_tan_up = -r_up * math.sin(beta)
    x_line_c = np.linspace(-l_conv, x_tan_up, npts // 4)
    y_line_c = r_c - (x_line_c + l_conv) * math.tan(beta)
    th = np.linspace(-math.pi / 2 - beta, -math.pi / 2, npts // 4)
    x_arc_c = r_up * np.cos(th)
    y_arc_c = r_up * np.sin(th) + r_up + r_t

    # arco de salida de garganta: 0.382 r_t, de -90 deg a (theta_n - 90 deg)
    r_dn = 0.382 * r_t
    th = np.linspace(-math.pi / 2, theta_n - math.pi / 2, npts // 4)
    x_arc_d = r_dn * np.cos(th)
    y_arc_d = r_dn * np.sin(th) + r_dn + r_t

    # Bezier cuadrática N -> Q -> E
    Nx, Ny = x_arc_d[-1], y_arc_d[-1]
    Ex, Ey = l_div, r_e
    m1, m2 = math.tan(theta_n), math.tan(theta_e)
    c1, c2 = Ny - m1 * Nx, Ey - m2 * Ex
    if abs(m1 - m2) < 1e-9:
        raise ValueError("theta_n y theta_e casi iguales: la Bezier degenera.")
    Qx = (c2 - c1) / (m1 - m2)
    Qy = m1 * Qx + c1
    t = np.linspace(0.0, 1.0, npts // 2)
    x_bez = (1 - t) ** 2 * Nx + 2 * (1 - t) * t * Qx + t ** 2 * Ex
    y_bez = (1 - t) ** 2 * Ny + 2 * (1 - t) * t * Qy + t ** 2 * Ey

    x = np.concatenate([x_line_c, x_arc_c, x_arc_d, x_bez])
    y = np.concatenate([y_line_c, y_arc_c, y_arc_d, y_bez])
    return x, y, theta_n, beta


# =====================================================================
# Resultado del diseño
# =====================================================================
@dataclass
class NozzleDesign:
    prop: Propellant
    p_c: float
    p_a: float
    p_e: float
    eps: float
    M_e: float
    r_t: float
    r_e: float
    r_c: float
    l_conv: float
    l_div: float
    alpha: float            # semiángulo divergente [rad]
    beta: float             # semiángulo convergente [rad]
    theta_n: float = 0.0    # solo campana [rad]
    theta_e: float = 0.0    # solo campana [rad]
    contour: str = "conical"
    bell_pct: float = 0.0
    lam: float = 1.0        # factor de pérdida por divergencia
    mdot: float = 0.0
    cf_mom: float = 0.0
    cf: float = 0.0
    thrust: float = 0.0
    isp: float = 0.0
    kn: float | None = None
    a_b: float | None = None
    r_burn: float = 0.0
    x: np.ndarray = field(default=None, repr=False)
    y: np.ndarray = field(default=None, repr=False)
    warnings: list[str] = field(default_factory=list)

    # ---- conveniencias en unidades de taller --------------------------
    @property
    def d_t_mm(self): return 2e3 * self.r_t
    @property
    def d_e_mm(self): return 2e3 * self.r_e
    @property
    def d_c_mm(self): return 2e3 * self.r_c
    @property
    def alpha_deg(self): return math.degrees(self.alpha)
    @property
    def beta_deg(self): return math.degrees(self.beta)


# =====================================================================
# Diseño
# =====================================================================
def design_nozzle(
    prop: Propellant,
    p_c: float,
    *,
    d_t: float | None = None,
    a_b: float | None = None,
    p_a: float = P_ATM,
    p_e: float | None = None,
    eps: float | None = None,
    d_c: float = 0.065,
    l_div: float = 0.0325,
    l_conv: float = 0.035,
    contour: str = "conical",
    k_up: float = 1.5,
    k_dn: float = 0.5,
) -> NozzleDesign:
    """Diseña la tobera. Devuelve un `NozzleDesign` completo.

    Garganta: se da `d_t` [m] directamente, o `a_b` [m^2] (área de quemado del
    grano) y se resuelve por el equilibrio de Saint-Robert.
    Expansión: se da `eps`, o `p_e` [Pa], o por defecto se adapta a `p_a`.
    """
    warn: list[str] = []

    # ---------------- garganta ----------------------------------------
    if d_t is None and a_b is None:
        raise ValueError("Hay que dar el diámetro de garganta (--dt) o el área de quemado (--ab).")
    if d_t is not None:
        r_t = 0.5 * d_t
        a_t = math.pi * r_t ** 2
    else:
        # mdot generado = mdot evacuado:  rho*Ab*a*Pc^n = Pc*At/c*
        a_t = prop.rho * a_b * prop.a * prop.c_star * p_c ** (prop.n - 1.0)
        r_t = math.sqrt(a_t / math.pi)
    a_e_over_a_t_given = eps

    kn = (a_b / a_t) if a_b is not None else None
    if kn is not None and not (120.0 <= kn <= 500.0):
        warn.append(f"Kn = {kn:.0f} fuera del rango habitual 150-400: revisar grano o garganta.")

    # ---------------- expansión ---------------------------------------
    if a_e_over_a_t_given is not None:
        eps_v = a_e_over_a_t_given
        M_e = mach_from_area_ratio(eps_v, prop.gamma, supersonic=True)
        p_e_v = p_c * pressure_ratio_from_mach(M_e, prop.gamma)
    else:
        p_e_v = p_a if p_e is None else p_e
        M_e = mach_from_pressure_ratio(p_c / p_e_v, prop.gamma)
        eps_v = area_ratio_from_mach(M_e, prop.gamma)

    r_e = r_t * math.sqrt(eps_v)
    r_c = 0.5 * d_c
    if r_c <= r_t:
        raise ValueError("El radio de cámara debe ser mayor que el de garganta.")

    # ---------------- geometría y ángulos ------------------------------
    theta_n = theta_e = 0.0
    bell_pct = 0.0
    if contour == "conical":
        x, y, alpha, beta = contour_conical(r_t, r_e, r_c, l_div, l_conv, k_up, k_dn)
        lam = 0.5 * (1.0 + math.cos(alpha))
    elif contour == "bell":
        l_ref = (math.sqrt(eps_v) - 1.0) * r_t / math.tan(math.radians(15.0))
        bell_pct = 100.0 * l_div / l_ref
        tn_d, te_d, w = rao_angles(eps_v, bell_pct)
        warn += w
        theta_n, theta_e = math.radians(tn_d), math.radians(te_d)
        x, y, alpha, beta = contour_bell(r_t, r_e, r_c, l_div, l_conv, theta_n, theta_e)
        lam = 0.5 * (1.0 + math.cos(theta_e))
    else:
        raise ValueError("contour debe ser 'conical' o 'bell'.")

    # ---------------- prestaciones ------------------------------------
    a_t_real = math.pi * r_t ** 2
    a_e = math.pi * r_e ** 2
    mdot = p_c * a_t_real / prop.c_star
    cfm = cf_momentum(p_c, p_e_v, prop.gamma)
    cf = lam * cfm + (p_e_v - p_a) / p_c * eps_v
    thrust = cf * p_c * a_t_real
    isp = thrust / (mdot * G0)

    # ---------------- avisos de diseño ---------------------------------
    if p_e_v < 0.4 * p_a:
        warn.append(
            f"Pe/Pa = {p_e_v / p_a:.2f} < 0.4 (criterio de Summerfield): "
            "riesgo de desprendimiento de la capa límite dentro del divergente."
        )
    elif p_e_v < p_a:
        warn.append(f"Tobera sobreexpandida (Pe/Pa = {p_e_v / p_a:.2f}): empuje por debajo del óptimo.")
    elif p_e_v > 1.25 * p_a:
        warn.append(f"Tobera subexpandida (Pe/Pa = {p_e_v / p_a:.2f}): queda expansión sin aprovechar.")

    ad = math.degrees(alpha)
    if contour == "conical" and not (12.0 <= ad <= 18.0):
        warn.append(
            f"Semiángulo divergente {ad:.1f} deg fuera del rango habitual 12-18 deg. "
            + ("Alargar el divergente." if ad > 18.0 else "Acortarlo o subir eps.")
        )
    bd = math.degrees(beta)
    if not (25.0 <= bd <= 50.0):
        warn.append(f"Semiángulo convergente {bd:.1f} deg fuera del rango habitual 30-45 deg.")

    return NozzleDesign(
        prop=prop, p_c=p_c, p_a=p_a, p_e=p_e_v, eps=eps_v, M_e=M_e,
        r_t=r_t, r_e=r_e, r_c=r_c, l_conv=l_conv, l_div=l_div,
        alpha=alpha, beta=beta, theta_n=theta_n, theta_e=theta_e,
        contour=contour, bell_pct=bell_pct, lam=lam,
        mdot=mdot, cf_mom=cfm, cf=cf, thrust=thrust, isp=isp,
        kn=kn, a_b=a_b, r_burn=prop.burn_rate(p_c),
        x=x, y=y, warnings=warn,
    )


def axial_profile(d: NozzleDesign):
    """Mach, P/Pc y T/Tc a lo largo del contorno. Devuelve (x, M, p_ratio, t_ratio)."""
    g = d.prop.gamma
    eps_x = (d.y / d.r_t) ** 2
    M = np.empty_like(eps_x)
    for i, (e, xi) in enumerate(zip(eps_x, d.x)):
        e = max(e, 1.0)
        M[i] = mach_from_area_ratio(e, g, supersonic=(xi > 0.0))
    return d.x, M, pressure_ratio_from_mach(M, g), temperature_ratio_from_mach(M, g)


# =====================================================================
# Informe
# =====================================================================
def report(d: NozzleDesign) -> str:
    L = []
    w = 58
    L.append("=" * w)
    L.append("  DISEÑO DE TOBERA - RESULTADOS")
    L.append("=" * w)
    L.append(f"  Propelente             {d.prop.name}")
    if d.prop.source:
        L.append(f"    fuente               {d.prop.source}")
    L.append(f"    gamma / M / Tc       {d.prop.gamma:.3f} / "
             f"{d.prop.M * 1e3:.2f} g/mol / {d.prop.T_c:.0f} K")
    L.append(f"    c* ideal / efectiva  {d.prop.c_star_ideal:.1f} / {d.prop.c_star:.1f} m/s"
             f"  (eta = {d.prop.eta_cstar:.2f})")
    L.append(f"    r a Pc               {d.r_burn * 1e3:.2f} mm/s")
    L.append("-" * w)
    L.append("  CONDICIONES")
    L.append(f"    Presión de cámara    {d.p_c / 1e5:.2f} bar")
    L.append(f"    Presión de salida    {d.p_e / 1e5:.3f} bar   (Pe/Pa = {d.p_e / d.p_a:.2f})")
    L.append(f"    Presión ambiente     {d.p_a / 1e5:.3f} bar")
    L.append("-" * w)
    L.append("  GEOMETRÍA")
    L.append(f"    D garganta           {d.d_t_mm:.2f} mm")
    L.append(f"    D salida             {d.d_e_mm:.2f} mm")
    L.append(f"    D cámara             {d.d_c_mm:.2f} mm")
    L.append(f"    Relación expansión   {d.eps:.3f}")
    L.append(f"    Mach de salida       {d.M_e:.3f}")
    L.append(f"    L convergente        {d.l_conv * 1e3:.2f} mm")
    L.append(f"    L divergente         {d.l_div * 1e3:.2f} mm")
    if d.kn is not None:
        L.append(f"    Kn = Ab/At           {d.kn:.0f}")
    L.append("-" * w)
    L.append("  ÁNGULOS  (salida del cálculo, no entrada)")
    L.append(f"    Semiángulo converg.  {d.beta_deg:.2f} deg      (total {2 * d.beta_deg:.2f} deg)")
    if d.contour == "conical":
        L.append(f"    Semiángulo diverg.   {d.alpha_deg:.2f} deg      (total {2 * d.alpha_deg:.2f} deg)")
        a_ideal = math.degrees(math.atan((d.r_e - d.r_t) / d.l_div))
        L.append(f"      cono ideal sin arco  {a_ideal:.2f} deg")
    else:
        L.append(f"    Theta_n (inicial)    {math.degrees(d.theta_n):.2f} deg")
        L.append(f"    Theta_e (salida)     {math.degrees(d.theta_e):.2f} deg")
        L.append(f"    Campana              {d.bell_pct:.1f} % de un cono de 15 deg")
    L.append(f"    Factor divergencia   lambda = {d.lam:.4f}")
    L.append("-" * w)
    L.append("  PRESTACIONES")
    L.append(f"    Gasto másico         {d.mdot:.4f} kg/s")
    L.append(f"    CF (cantidad mov.)   {d.cf_mom:.4f}")
    L.append(f"    CF efectivo          {d.cf:.4f}")
    L.append(f"    Empuje               {d.thrust:.1f} N")
    L.append(f"    Isp                  {d.isp:.1f} s")
    L.append("=" * w)
    if d.warnings:
        L.append("  AVISOS")
        for s in d.warnings:
            L.append(f"    [!] {s}")
        L.append("=" * w)
    return "\n".join(L)


# =====================================================================
# Gráfico
# =====================================================================
def plot_nozzle(d: NozzleDesign, savepath: str | None = None, show: bool = False):
    """Corte transversal 2D acotado, con la distribución axial de Mach y presión."""
    import matplotlib
    if savepath and not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Arc

    mm = 1e3
    x, M, pr, _ = axial_profile(d)
    xs, ys = d.x * mm, d.y * mm

    fig = plt.figure(figsize=(11.0, 8.2))
    gs = fig.add_gridspec(2, 2, height_ratios=[2.5, 1.0], hspace=0.42, wspace=0.26,
                          left=0.085, right=0.975, top=0.90, bottom=0.085)
    ax = fig.add_subplot(gs[0, :])

    # ---- gas y pared ---------------------------------------------------
    ax.fill_between(xs, -ys, ys, color=C_GAS, zorder=1)
    wall = 0.14 * (ys.max() - ys.min()) + 0.9
    for s in (1, -1):
        ax.fill_between(xs, s * ys, s * (ys + wall), color=C_WALL, alpha=0.90,
                        linewidth=0, zorder=2)
        ax.plot(xs, s * ys, color=C_WALL, lw=1.6, zorder=3)

    # ---- eje y estaciones ---------------------------------------------
    ax.axhline(0, color=C_AXIS, lw=0.9, ls=(0, (7, 3, 1.5, 3)), zorder=2)
    for xv, lab in ((0.0, "garganta"), (d.l_div * mm, "salida"), (-d.l_conv * mm, "cámara")):
        ax.axvline(xv, color=C_AXIS, lw=0.7, ls=":", alpha=0.75, zorder=2)
        ax.text(xv, -(ys.max() + wall) * 1.14, lab, ha="center", va="top",
                fontsize=8, color=C_NOTE)

    # ---- ángulo divergente --------------------------------------------
    r_dn = (0.382 if d.contour == "bell" else 0.5) * d.r_t
    a_div = d.theta_n if d.contour == "bell" else d.alpha
    xt = r_dn * math.sin(a_div) * mm
    yt = (d.r_t + r_dn * (1 - math.cos(a_div))) * mm
    ln = 0.52 * d.l_div * mm
    ax.plot([xt, xt + ln], [yt, yt], color=C_PRES, lw=1.1, ls="--", zorder=5)
    ax.plot([xt, xt + ln * math.cos(a_div)], [yt, yt + ln * math.sin(a_div)],
            color=C_PRES, lw=1.1, ls="--", zorder=5)
    ax.add_patch(Arc((xt, yt), ln, ln, theta1=0, theta2=math.degrees(a_div),
                     color=C_PRES, lw=1.5, zorder=5))
    lbl = r"$\theta_n$" if d.contour == "bell" else r"$\alpha$"
    ax.text(xt + ln * 0.62 * math.cos(a_div / 2), yt + ln * 0.62 * math.sin(a_div / 2),
            f"{lbl} = {math.degrees(a_div):.1f}°", color=C_PRES, fontsize=10.5,
            fontweight="bold", ha="left", va="bottom", zorder=6)

    # ---- ángulo convergente -------------------------------------------
    r_up = 1.5 * d.r_t
    xb = -r_up * math.sin(d.beta) * mm
    yb = (d.r_t + r_up * (1 - math.cos(d.beta))) * mm
    lc = 0.62 * d.l_conv * mm
    ax.plot([xb - lc, xb], [yb, yb], color=C_MACH, lw=1.1, ls="--", zorder=5)
    ax.plot([xb - lc * math.cos(d.beta), xb], [yb + lc * math.sin(d.beta), yb],
            color=C_MACH, lw=1.1, ls="--", zorder=5)
    ax.add_patch(Arc((xb, yb), lc, lc, theta1=180 - math.degrees(d.beta), theta2=180,
                     color=C_MACH, lw=1.5, zorder=5))
    ax.text(xb - lc * 0.66 * math.cos(d.beta / 2), yb + lc * 0.66 * math.sin(d.beta / 2),
            rf"$\beta$ = {d.beta_deg:.1f}°", color=C_MACH, fontsize=10.5,
            fontweight="bold", ha="right", va="bottom", zorder=6)

    # ---- cotas de diámetro --------------------------------------------
    def dim_v(xv, r, text, dx):
        ax.annotate("", xy=(xv, r), xytext=(xv, -r),
                    arrowprops=dict(arrowstyle="<->", color=C_NOTE, lw=1.0), zorder=6)
        ax.text(xv + dx, 0, text, rotation=90, ha="center", va="center",
                fontsize=8.5, color=C_NOTE,
                bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.4), zorder=7)

    sp = 0.035 * (xs.max() - xs.min())
    dim_v(0.0, d.r_t * mm, f"Ø{d.d_t_mm:.1f}", sp)
    dim_v(d.l_div * mm, d.r_e * mm, f"Ø{d.d_e_mm:.1f}", -sp)
    dim_v(-d.l_conv * mm, d.r_c * mm, f"Ø{d.d_c_mm:.1f}", sp)

    ax.set_xlabel("x [mm]  ·  origen en la garganta")
    ax.set_ylabel("r [mm]")
    kind = "cónica" if d.contour == "conical" else f"acampanada TOP ({d.bell_pct:.0f} %)"
    ax.set_title(
        f"Corte transversal — tobera {kind}   ·   "
        f"ε = {d.eps:.2f}   ·   F = {d.thrust:.0f} N   ·   Isp = {d.isp:.0f} s",
        fontsize=12, fontweight="bold", pad=12)
    ax.set_aspect("equal")
    ax.grid(True, color=C_AXIS, alpha=0.16, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.margins(x=0.04, y=0.20)

    # ---- Mach ----------------------------------------------------------
    ax1 = fig.add_subplot(gs[1, 0])
    ax1.plot(x * mm, M, color=C_MACH, lw=2.0)
    ax1.axhline(1.0, color=C_AXIS, lw=0.9, ls="--")
    ax1.axvline(0.0, color=C_AXIS, lw=0.7, ls=":")
    ax1.annotate(f"M = {d.M_e:.2f}", xy=(d.l_div * mm, d.M_e),
                 xytext=(-6, -2), textcoords="offset points",
                 ha="right", va="top", fontsize=9, color=C_MACH, fontweight="bold")
    ax1.text(0.02, 0.93, "M = 1", transform=ax1.transAxes, fontsize=8, color=C_NOTE)
    ax1.set_title("Número de Mach", fontsize=10, fontweight="bold", loc="left")
    ax1.set_xlabel("x [mm]")
    ax1.set_ylabel("M [-]")

    # ---- presión (panel aparte: nunca dos escalas en un mismo eje) ------
    ax2 = fig.add_subplot(gs[1, 1])
    ax2.plot(x * mm, pr * d.p_c / 1e5, color=C_PRES, lw=2.0)
    ax2.axhline(d.p_a / 1e5, color=C_AXIS, lw=0.9, ls="--")
    ax2.axvline(0.0, color=C_AXIS, lw=0.7, ls=":")
    ax2.annotate(f"{d.p_e / 1e5:.2f} bar", xy=(d.l_div * mm, d.p_e / 1e5),
                 xytext=(-6, 8), textcoords="offset points",
                 ha="right", va="bottom", fontsize=9, color=C_PRES, fontweight="bold")
    ax2.text(0.02, 0.06, "ambiente", transform=ax2.transAxes, fontsize=8, color=C_NOTE)
    ax2.set_title("Presión estática", fontsize=10, fontweight="bold", loc="left")
    ax2.set_xlabel("x [mm]")
    ax2.set_ylabel("P [bar]")

    for a in (ax1, ax2):
        a.grid(True, color=C_AXIS, alpha=0.16, lw=0.6)
        a.set_axisbelow(True)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)

    if savepath:
        fig.savefig(savepath, dpi=160, bbox_inches="tight", facecolor="white")
        print(f"[ok] gráfico guardado en {savepath}")
    if show:
        plt.show()
    return fig


# =====================================================================
# CLI
# =====================================================================
def main(argv=None):
    p = argparse.ArgumentParser(
        description="Diseño interno de tobera para motor de propelente sólido.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    g = p.add_argument_group("propelente")
    g.add_argument("--preset", choices=sorted(PRESETS), default="apcp")
    g.add_argument("--gamma", type=float, help="sobreescribe gamma")
    g.add_argument("--molar-mass", type=float, help="sobreescribe M [g/mol]")
    g.add_argument("--tc", type=float, help="sobreescribe Tc [K]")
    g.add_argument("--rho", type=float, help="sobreescribe densidad [kg/m3]")
    g.add_argument("--eta-cstar", type=float, default=0.95, help="eficiencia de c*")

    g = p.add_argument_group("condiciones")
    g.add_argument("--pc", type=float, default=50.0, help="presión de cámara [bar]")
    g.add_argument("--pa", type=float, default=1.01325, help="presión ambiente [bar]")
    g.add_argument("--pe", type=float, default=None,
                   help="presión de salida objetivo [bar]; por defecto adaptada a --pa")
    g.add_argument("--eps", type=float, default=None,
                   help="relación de expansión impuesta (tiene prioridad sobre --pe)")

    g = p.add_argument_group("geometría")
    g.add_argument("--dt", type=float, default=10.6, help="diámetro de garganta [mm]")
    g.add_argument("--ab", type=float, default=None,
                   help="área de quemado del grano [mm2]; si se da, calcula --dt por Kn")
    g.add_argument("--dc", type=float, default=65.0, help="diámetro interior de cámara [mm]")
    g.add_argument("--l-div", type=float, default=32.5, help="longitud del divergente [mm]")
    g.add_argument("--l-conv", type=float, default=35.0, help="longitud del convergente [mm]")
    g.add_argument("--contour", choices=("conical", "bell"), default="conical")
    g.add_argument("--k-up", type=float, default=1.5, help="radio de acuerdo aguas arriba / rt")
    g.add_argument("--k-dn", type=float, default=0.5, help="radio de acuerdo aguas abajo / rt")

    g = p.add_argument_group("salida")
    g.add_argument("-o", "--out", default="tobera.png", help="fichero PNG de salida")
    g.add_argument("--show", action="store_true", help="abrir ventana interactiva")
    g.add_argument("--csv", default=None, help="exporta el contorno a CSV (x_mm, r_mm)")
    g.add_argument("--no-plot", action="store_true")

    args = p.parse_args(argv)

    prop = PRESETS[args.preset]()
    if args.gamma is not None:      prop.gamma = args.gamma
    if args.molar_mass is not None: prop.M = args.molar_mass * 1e-3
    if args.tc is not None:         prop.T_c = args.tc
    if args.rho is not None:        prop.rho = args.rho
    prop.eta_cstar = args.eta_cstar

    d = design_nozzle(
        prop, p_c=args.pc * 1e5,
        d_t=None if args.ab else args.dt * 1e-3,
        a_b=args.ab * 1e-6 if args.ab else None,
        p_a=args.pa * 1e5,
        p_e=args.pe * 1e5 if args.pe else None,
        eps=args.eps,
        d_c=args.dc * 1e-3,
        l_div=args.l_div * 1e-3,
        l_conv=args.l_conv * 1e-3,
        contour=args.contour,
        k_up=args.k_up, k_dn=args.k_dn,
    )
    print(report(d))

    if args.csv:
        np.savetxt(args.csv, np.column_stack([d.x * 1e3, d.y * 1e3]),
                   delimiter=",", header="x_mm,r_mm", comments="", fmt="%.4f")
        print(f"[ok] contorno exportado a {args.csv}")

    if not args.no_plot:
        plot_nozzle(d, savepath=args.out, show=args.show)
    return d


if __name__ == "__main__":
    main()
