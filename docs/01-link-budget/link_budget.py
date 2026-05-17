#!/usr/bin/env python3
"""
IRM 雷达式液压缸位置传感器 - 链路预算与波导分析

可独立运行，复现 docs/01-link-budget/ 下两份文档的所有数值。

依赖：numpy（可选 matplotlib，仅用于绘图）
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

# ---------------------------- 物理常数 ----------------------------
C0 = 2.99792458e8          # 真空光速 m/s
ETA0 = 376.730313668       # 自由空间波阻抗 Ω
MU0 = 4 * math.pi * 1e-7   # 真空磁导率
K_BOLTZ = 1.380649e-23     # 玻尔兹曼
T_REF = 290.0              # 噪声温度参考 K

# Bessel 根（圆波导）
P_PRIME = {  # TE 模：J_n'(x)=0
    (1, 1): 1.8411837,
    (2, 1): 3.0542369,
    (0, 1): 3.8317060,     # TE01
    (3, 1): 4.2011889,
    (4, 1): 5.3175531,
    (1, 2): 5.3314427,
}
P_ROOT = {   # TM 模：J_n(x)=0
    (0, 1): 2.4048256,     # TM01
    (1, 1): 3.8317060,     # TM11 (与 TE01 简并)
    (2, 1): 5.1356223,
    (0, 2): 5.5200781,     # TM02
    (3, 1): 6.3801619,
    (1, 2): 7.0155867,
    (0, 3): 8.6537279,     # TM03
}


# ---------------------------- 介质模型 ----------------------------
@dataclass(frozen=True)
class Oil:
    name: str
    eps_r: float
    tan_delta: float       # @ 24 GHz, 25 °C

    @property
    def n(self) -> float:
        return math.sqrt(self.eps_r)


OILS = {
    "HM46_clean":  Oil("ISO HM46 矿物油 (洁净)",   2.20, 0.0008),
    "HV46_clean":  Oil("ISO HV46 矿物油 (洁净)",   2.20, 0.0010),
    "HEES":        Oil("ISO HEES 酯基",            2.45, 0.0030),
    "HM46_wet01":  Oil("HM46 含 0.1% 水",          2.25, 0.0015),
    "HM46_wet05":  Oil("HM46 含 0.5% 水",          2.32, 0.0050),
}
DEFAULT_OIL = OILS["HV46_clean"]


# ---------------------------- 波导计算 ----------------------------
def cutoff_freq(p: float, a: float, n: float) -> float:
    """圆波导截止频率，p 为 Bessel 根，a 为半径(m)，n 折射率"""
    return p * C0 / (2 * math.pi * a * n)


def mode_count(f: float, a: float, n: float) -> int:
    """Weyl 公式估算 f 处传播模式数量"""
    k = 2 * math.pi * f * n / C0
    return int((a * k) ** 2 / 4)


def alpha_dielectric(f: float, oil: Oil) -> float:
    """介质损耗系数 [Np/m]"""
    return math.pi * f * oil.tan_delta * oil.n / C0


def alpha_conductor_tm01(f: float, a: float, oil: Oil,
                         sigma_steel: float = 1.4e6) -> float:
    """TM01 在圆波导内的导体损耗 [Np/m]"""
    Rs = math.sqrt(math.pi * f * MU0 / sigma_steel)
    fc = cutoff_freq(P_ROOT[(0, 1)], a, oil.n)
    if f <= fc:
        return float("inf")
    eta = ETA0 / oil.n
    return Rs / (eta * a * math.sqrt(1 - (fc / f) ** 2))


def group_velocity(f: float, p: float, a: float, oil: Oil) -> float:
    fc = cutoff_freq(p, a, oil.n)
    if f <= fc:
        return 0.0
    return (C0 / oil.n) * math.sqrt(1 - (fc / f) ** 2)


# ---------------------------- 链路预算 ----------------------------
@dataclass
class LinkParams:
    f_c: float = 24.125e9
    B: float = 250e6
    T_chirp: float = 250e-6
    P_tx_dbm: float = 10.0
    L_probe_db: float = 1.5     # 单程
    L_window_db: float = 1.0    # 单程
    L_piston_db: float = 0.5
    NF_db: float = 12.0
    rx_gain_db: float = 10.0    # MMIC 内部 IF 链
    fft_N: int = 1024
    bandwidth_if_hz: float = 25e3


def path_loss_total(d_m: float, oil: Oil, p: LinkParams) -> float:
    """往返总损耗 dB"""
    alpha_np = alpha_dielectric(p.f_c, oil)
    alpha_db = alpha_np * 8.686
    return 2 * alpha_db * d_m + 2 * (p.L_probe_db + p.L_window_db) + p.L_piston_db


def if_freq(d_m: float, oil: Oil, p: LinkParams) -> float:
    return 2 * p.B * d_m * oil.n / (C0 * p.T_chirp)


def noise_floor_dbm(p: LinkParams, bw_hz: float | None = None) -> float:
    bw = bw_hz if bw_hz is not None else p.fft_N and (1 / p.T_chirp)
    kT_dbm_hz = 10 * math.log10(K_BOLTZ * T_REF * 1000)
    return kT_dbm_hz + 10 * math.log10(bw) + p.NF_db


def snr_db(d_m: float, oil: Oil, p: LinkParams) -> float:
    p_if_dbm = p.P_tx_dbm - path_loss_total(d_m, oil, p) + p.rx_gain_db
    fft_bw = 1 / p.T_chirp
    nf_dbm = noise_floor_dbm(p, fft_bw)
    return p_if_dbm - nf_dbm


def sigma_d_crlb(snr_db_val: float, p: LinkParams, oil: Oil) -> float:
    """CRLB 距离估计标准差 m"""
    snr_lin = 10 ** (snr_db_val / 10)
    return C0 * oil.n / (4 * math.pi * p.f_c * math.sqrt(2 * snr_lin))


# ---------------------------- 报告生成 ----------------------------
def hr(title: str = "", char: str = "=") -> None:
    print()
    print(char * 78)
    if title:
        print(title)
        print(char * 78)


def print_oil_table(p: LinkParams) -> None:
    hr("油品介质损耗 @ {:.3f} GHz".format(p.f_c / 1e9))
    print(f"{'油品':<28} {'tan δ':>8} {'α (Np/m)':>10} {'α (dB/m)':>10}")
    for o in OILS.values():
        a_np = alpha_dielectric(p.f_c, o)
        print(f"{o.name:<28} {o.tan_delta:>8.4f} {a_np:>10.3f} {a_np*8.686:>10.2f}")


def print_cutoff_table(oil: Oil) -> None:
    hr(f"圆波导截止频率 (在 {oil.name}, n={oil.n:.3f})")
    diameters_mm = [25, 50, 80, 100, 150, 200]
    print(f"{'D (mm)':>8} | {'TE11 (GHz)':>12} {'TM01 (GHz)':>12} "
          f"{'TM02 (GHz)':>12}")
    for D in diameters_mm:
        a = D / 2 / 1000
        te11 = cutoff_freq(P_PRIME[(1, 1)], a, oil.n) / 1e9
        tm01 = cutoff_freq(P_ROOT[(0, 1)], a, oil.n) / 1e9
        tm02 = cutoff_freq(P_ROOT[(0, 2)], a, oil.n) / 1e9
        print(f"{D:>8} | {te11:>12.2f} {tm01:>12.2f} {tm02:>12.2f}")


def print_mode_count_table(oil: Oil) -> None:
    hr(f"传播模式总数估计 (Weyl 公式, {oil.name})")
    diameters_mm = [25, 50, 80, 100, 150, 200]
    print(f"{'D (mm)':>8} | {'24 GHz':>10} {'77 GHz':>10}")
    for D in diameters_mm:
        a = D / 2 / 1000
        n24 = mode_count(24e9, a, oil.n)
        n77 = mode_count(77e9, a, oil.n)
        print(f"{D:>8} | {n24:>10} {n77:>10}")


def print_link_budget(oil: Oil, p: LinkParams) -> None:
    hr(f"24 GHz 链路预算 ({oil.name})")
    ds_mm = [50, 100, 250, 500, 1000, 1500, 2000]
    print(f"{'d (mm)':>8} {'f_b (kHz)':>10} {'L (dB)':>8} "
          f"{'P_if (dBm)':>11} {'SNR (dB)':>9} {'σ_d (µm)':>10}")
    for d_mm in ds_mm:
        d = d_mm / 1000
        fb = if_freq(d, oil, p) / 1e3
        L = path_loss_total(d, oil, p)
        Pif = p.P_tx_dbm - L + p.rx_gain_db
        S = snr_db(d, oil, p)
        sd = sigma_d_crlb(S, p, oil) * 1e6  # µm
        print(f"{d_mm:>8} {fb:>10.2f} {L:>8.2f} {Pif:>11.2f} {S:>9.1f} "
              f"{sd:>10.3f}")


def print_group_velocity(oil: Oil) -> None:
    hr(f"D=50mm 时各模式群速 @ 24 GHz ({oil.name})")
    a = 0.025
    f = 24e9
    print(f"{'mode':<10} {'p root':>10} {'fc (GHz)':>10} "
          f"{'vg (×10^8 m/s)':>16} {'vg/(c/n)':>10}")
    for name, p_root in [("TM01", P_ROOT[(0, 1)]),
                         ("TM02", P_ROOT[(0, 2)]),
                         ("TM03", P_ROOT[(0, 3)])]:
        fc = cutoff_freq(p_root, a, oil.n) / 1e9
        vg = group_velocity(f, p_root, a, oil)
        print(f"{name:<10} {p_root:>10.4f} {fc:>10.2f} "
              f"{vg/1e8:>16.3f} {vg / (C0/oil.n):>10.4f}")


def main() -> None:
    params = LinkParams()
    oil = DEFAULT_OIL

    print("\nIRM 雷达式液压缸位置传感器 - 链路预算与波导分析\n")
    print(f"中心频率 f_c    = {params.f_c/1e9:.3f} GHz")
    print(f"扫频带宽 B      = {params.B/1e6:.0f} MHz")
    print(f"Chirp 周期 T    = {params.T_chirp*1e6:.0f} µs")
    print(f"默认油品        = {oil.name} (ε_r={oil.eps_r}, n={oil.n:.4f})")
    print(f"自由空间波长 λ0 = {C0/params.f_c*1000:.3f} mm")
    print(f"油中波长 λ_oil  = {C0/(params.f_c*oil.n)*1000:.3f} mm")
    print(f"油中相速 v_oil  = {C0/oil.n/1e8:.4f} ×10^8 m/s")

    print_oil_table(params)
    print_cutoff_table(oil)
    print_mode_count_table(oil)
    print_link_budget(oil, params)
    print_group_velocity(oil)

    # CRLB 表
    hr("CRLB 距离精度 vs SNR")
    for snr in [50, 60, 70, 80, 90]:
        sd_um = sigma_d_crlb(snr, params, oil) * 1e6
        print(f"  SNR = {snr:>2} dB  →  σ_d = {sd_um:>8.3f} µm")

    # 设计裕度判断
    hr("设计裕度自检")
    d_check = 2.0
    snr_check = snr_db(d_check, oil, params)
    margin = snr_check - 50  # 50 dB 为最低工作 SNR
    print(f"d = {d_check} m 时 SNR = {snr_check:.1f} dB, "
          f"相对 50 dB 工作下限裕度 = {margin:.1f} dB")
    assert margin > 30, "余量不足 30 dB，回查链路！"
    print("PASS: 链路余量充足。")

    # 油参数敏感性扫描 (供客户确认)
    hr("油参数敏感性 — 供客户/油品供应商确认", char="*")
    print("以下 5 项参数最终精度由客户实际用油决定。"
          "需要从油品 MSDS 或独立测试 (24 GHz 频段) 获得：\n")
    print(" 1) 25 °C 下的 ε_r")
    print(" 2) 24 GHz 下的 tan δ")
    print(" 3) dε_r/dT 温度系数")
    print(" 4) 含水率上限 (运行期允许的最大值)")
    print(" 5) 是否换油 / 同一台机器是否会切换油品\n")

    hr("油 ε_r 不确定度 → 距离误差")
    d_test = 1.0   # m
    base_n = math.sqrt(2.20)
    print(f"基准 ε_r = 2.20, n = {base_n:.4f}")
    print(f"{'ε_r':>6} {'n':>8} {'相对距离误差':>14}")
    for eps in [2.05, 2.10, 2.15, 2.20, 2.25, 2.30, 2.35]:
        n = math.sqrt(eps)
        rel_err = (n - base_n) / base_n
        d_err_mm = rel_err * d_test * 1000
        print(f"{eps:>6.2f} {n:>8.4f} {d_err_mm:>+11.2f} mm/m")

    hr("油 tan δ → 2 m 处单程衰减")
    print(f"{'tan δ':>10} {'α (dB/m)':>10} {'2 m 单程 (dB)':>14}")
    for td in [3e-4, 5e-4, 8e-4, 1e-3, 1.5e-3, 3e-3, 5e-3, 1e-2]:
        a_db = math.pi * params.f_c * td * 1.483 / C0 * 8.686
        print(f"{td:>10.4f} {a_db:>10.2f} {a_db*2:>14.2f}")

    hr("温度漂移 — 假设 dε_r/dT = -1.5e-3 / °C")
    print(f"{'T (°C)':>8} {'ε_r':>8} {'每米距离漂移':>15}")
    for T in [-40, -20, 0, 25, 50, 80, 105]:
        dT = T - 25
        eps_T = 2.20 + (-1.5e-3) * dT
        n_T = math.sqrt(eps_T)
        rel_err = (n_T - base_n) / base_n
        print(f"{T:>+8d} {eps_T:>8.4f} {rel_err*1000:>+12.3f} mm/m")


if __name__ == "__main__":
    main()
