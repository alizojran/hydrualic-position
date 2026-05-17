#!/usr/bin/env python3
"""
Scherr–Ayhan 组合频率+相位估计算法 — FMCW 高精度测距仿真

复现以下两篇论文的核心算法并验证 CRB 性能：

  [1] S. Ayhan, S. Scherr, A. Bhutani, B. Fischbach, M. Pauli, T. Zwick,
      "High-Accuracy Range Detection Radar Sensor for Hydraulic Cylinders,"
      IEEE Trans. Microwave Theory Tech., vol. 62, no. 3, pp. 572–581, 2014.

  [2] S. Scherr, S. Ayhan, B. Fischbach, A. Bhutani, M. Pauli, T. Zwick,
      "An Efficient Frequency and Phase Estimation Algorithm With CRB
      Performance for FMCW Radar Applications,"
      IEEE Trans. Instrum. Meas., vol. 64, no. 7, pp. 1868–1875, 2015.

本脚本实现：
  1. FMCW IF 信号生成器 (可选 AWGN / PLL 相位噪声 / Chirp 非线性)
  2. 三步距离估计流水线：FFT → CZT → 相位求解
  3. Cramér–Rao 下界 (CRB₁: phase-unknown, CRB₂: phase-known) 计算
  4. Monte-Carlo 性能扫描 (RMSE vs SNR)
  5. 我们项目的双反射基准扩展 (探针自含基准 → 油 ε_r 实时估计)

依赖: numpy, scipy, matplotlib (matplotlib 仅用于绘图，可选)

运行: python3 scherr_ayhan_sim.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.signal import czt as scipy_czt

C0 = 2.99792458e8  # 真空光速 m/s


# ============================================================================
# 1. FMCW 系统参数
# ============================================================================
@dataclass
class FMCWParams:
    """FMCW 雷达系统参数 (默认对应我们的 24 GHz IRM 设计)"""
    f0: float = 24.125e9     # 中心频率 Hz
    B: float = 250e6         # 扫频带宽 Hz
    T: float = 250e-6        # Chirp 持续时间 s
    f_s: float = 2e6         # IF 采样率 Hz
    n_oil: float = 1.483     # 油介电介质折射率 sqrt(eps_r)

    @property
    def N(self) -> int:
        """每 chirp 采样点数"""
        return int(self.T * self.f_s)

    @property
    def lam0(self) -> float:
        """自由空间波长"""
        return C0 / self.f0

    @property
    def lam_med(self) -> float:
        """油介质波长 = λ₀ / n"""
        return C0 / (self.f0 * self.n_oil)

    @property
    def range_resolution(self) -> float:
        """理论距离分辨率 c / (2 B n)"""
        return C0 / (2 * self.B * self.n_oil)

    @property
    def dR_dfb(self) -> float:
        """距离对差拍频率的灵敏度 dR/df_b = c·T / (2·B·n)"""
        return C0 * self.T / (2 * self.B * self.n_oil)

    @property
    def dR_dphi(self) -> float:
        """距离对载频相位的灵敏度 dR/dφ = c / (4π·f₀·n)"""
        return C0 / (4 * math.pi * self.f0 * self.n_oil)


# ============================================================================
# 2. IF 信号生成 (理想 + 可选损伤)
# ============================================================================
def fmcw_if_signal(
    R: float,
    p: FMCWParams,
    snr_db: float = 40.0,
    phase_noise_dbc_hz: float = -200.0,
    chirp_nonlin_ppm: float = 0.0,
    seed: int | None = None,
) -> NDArray:
    """
    生成复基带 IF 信号 (deramping 后)

    单目标在距离 R 处的 IF 信号：
        s(t) = A · exp[j·(2π·f_b·t + φ_0)] + n(t)
    其中：
        f_b   = 2·B·n·R / (c·T)     差拍频率
        φ_0   = 4π·f_0·n·R / c      载频相位 (R 的另一个独立信息)

    参数
    ----
    R                  目标距离 (m)
    p                  FMCW 参数
    snr_db             单 chirp 内的 SNR (相对噪声平均功率)
    phase_noise_dbc_hz PLL 相位噪声 (在 1 kHz offset 大致水平, dBc/Hz)
                       <= -200 时关闭
    chirp_nonlin_ppm   chirp 非线性 (B(t)对 t 二阶项的 ppm 系数), 0 关闭
    seed               随机数种子，None 则随机
    """
    rng = np.random.default_rng(seed)
    N = p.N
    t = np.arange(N) / p.f_s

    # 理想差拍频率与载频相位
    f_b = 2 * p.B * p.n_oil * R / (C0 * p.T)
    phi_0 = 4 * math.pi * p.f0 * p.n_oil * R / C0

    # 理想信号
    A = 1.0
    if chirp_nonlin_ppm > 0:
        # 二阶非线性：f_inst(t) ≈ f0 + (B/T)·t · (1 + κ·t/T)
        # 等效在 IF 信号上引入 t² 项
        kappa = chirp_nonlin_ppm * 1e-6
        phase = 2 * math.pi * f_b * t * (1 + kappa * t / p.T) + phi_0
    else:
        phase = 2 * math.pi * f_b * t + phi_0

    s = A * np.exp(1j * phase)

    # 加性高斯白噪声 (复数: 实虚部各 σ/√2)
    if snr_db < 200:
        noise_std = A / 10 ** (snr_db / 20)
        n_re = rng.standard_normal(N) * noise_std / math.sqrt(2)
        n_im = rng.standard_normal(N) * noise_std / math.sqrt(2)
        s = s + (n_re + 1j * n_im)

    # 简化 PLL 相位噪声：1/f² 单边带积分 → chirp 内累积 σ_φ
    # 输入: L(f=1 kHz) [dBc/Hz], 假设 1/f² 直到 fs/2
    # σ_φ² = 2 · ∫ L(f) df = 2 · L(1k) · (1kHz)² · (1/f_low - 1/f_high)
    # 其中 f_low = 1/T (chirp 持续时间内最低相关频率)
    if phase_noise_dbc_hz > -180:
        L0 = 10 ** (phase_noise_dbc_hz / 10)  # SSB PSD @ 1 kHz, lin/Hz
        f_low = 1.0 / p.T
        f_high = p.f_s / 2
        var_phi = 2 * L0 * (1e3) ** 2 * (1.0 / f_low - 1.0 / f_high)
        sigma_phi = math.sqrt(var_phi)
        # 模拟为布朗相位游走 (1/f² 形)
        increments = rng.standard_normal(N) * sigma_phi / math.sqrt(N)
        walk = np.cumsum(increments)
        s = s * np.exp(1j * walk)

    return s


# ============================================================================
# 3. Cramér–Rao 下界
# ============================================================================
def crb_omega(snr_lin: float, N: int) -> float:
    """角频率 ω = 2π·f/fs 的 CRB (rad/sample, std)

    Rife & Boorstyn 1974, 复正弦的经典结果：
        var(ω̂) >= 12 / (SNR · N · (N²-1))
    """
    return math.sqrt(12.0 / (snr_lin * N * (N**2 - 1)))


def crb_phi(snr_lin: float, N: int) -> float:
    """初始相位 φ 的 CRB (rad, std)

    在频率已知前提下：var(φ̂) >= 2·(2N-1) / (SNR · N · (N+1))
    大 N 近似 2/(SNR·N) 略偏紧，给出精确表达式
    """
    return math.sqrt(2.0 * (2 * N - 1) / (snr_lin * N * (N + 1)))


def crb_range_freq_only(snr_lin: float, N: int, p: FMCWParams) -> float:
    """仅用频率信息估计 R 的 CRB (m, std) — 对应 CRB₁ (phase unknown)"""
    sigma_omega = crb_omega(snr_lin, N)
    sigma_fb = sigma_omega * p.f_s / (2 * math.pi)
    return sigma_fb * p.dR_dfb


def crb_range_joint(snr_lin: float, N: int, p: FMCWParams) -> float:
    """联合频率+相位估计 R 的 CRB (m, std) — 对应 CRB₂ (phase known)

    R 通过 ω 和 φ 同时观测：
        ω = α·R,  α = 4π·B·n / (c·T·fs)
        φ = β·R,  β = 4π·f₀·n / c
    复正弦 Fisher 信息：
        I_R = 2·SNR · [α²·Σn² + 2αβ·Σn + β²·N]
            ≈ 2·SNR · β²·N      (相位项主导，f₀ >> α·N·fs/(2π))
    """
    alpha = 4 * math.pi * p.B * p.n_oil / (C0 * p.T * p.f_s)
    beta = 4 * math.pi * p.f0 * p.n_oil / C0
    sn = np.arange(N)
    I_R = 2 * snr_lin * (
        alpha**2 * np.sum(sn**2)
        + 2 * alpha * beta * np.sum(sn)
        + beta**2 * N
    )
    return 1.0 / math.sqrt(I_R)


# ============================================================================
# 4. 三步估计算法
# ============================================================================
def estimate_fft(s: NDArray, p: FMCWParams) -> tuple[float, float]:
    """步骤 1：FFT + 抛物线插值求粗距离

    返回 (R_coarse, f_b_coarse)
    """
    N = len(s)
    win = np.hanning(N)
    S = np.fft.fft(s * win)
    half = N // 2

    k_max = int(np.argmax(np.abs(S[:half])))

    # 抛物线插值 (3 点 log-amplitude，Jacobsen 类似精度)
    if 0 < k_max < half - 1:
        a = math.log(abs(S[k_max - 1]) + 1e-30)
        b = math.log(abs(S[k_max]) + 1e-30)
        c_ = math.log(abs(S[k_max + 1]) + 1e-30)
        delta = 0.5 * (a - c_) / (a - 2 * b + c_)
    else:
        delta = 0.0

    k_est = k_max + delta
    f_b = k_est * p.f_s / N
    R = f_b * p.dR_dfb
    return R, f_b


def estimate_czt(
    s: NDArray, p: FMCWParams, f_b_coarse: float, M: int = 1024,
    span_bins: float = 4.0,
) -> tuple[float, float, NDArray]:
    """步骤 2：CZT 在 FFT 主峰附近做精细频率搜索

    Chirp Z 变换在 z 平面上沿弧线均匀取 M 个点，等价于在 [f_start, f_end]
    频段内做 M 点 DFT。Bluestein 算法 O(N log N)，可在 FPGA 实时实现。

    返回 (R_fine, f_b_fine, S_czt)
    """
    N = len(s)
    win = np.hanning(N)

    bin_width = p.f_s / N
    span = span_bins * bin_width
    f_start = f_b_coarse - span / 2
    f_end = f_b_coarse + span / 2

    # scipy.signal.czt: w = 圆周步进, a = 起始点
    a = np.exp(1j * 2 * math.pi * f_start / p.f_s)
    w = np.exp(-1j * 2 * math.pi * (f_end - f_start) / (M * p.f_s))
    S_czt = scipy_czt(s * win, m=M, w=w, a=a)

    m_max = int(np.argmax(np.abs(S_czt)))
    # 子-CZT-bin 抛物线插值
    if 0 < m_max < M - 1:
        aL = math.log(abs(S_czt[m_max - 1]) + 1e-30)
        bL = math.log(abs(S_czt[m_max]) + 1e-30)
        cL = math.log(abs(S_czt[m_max + 1]) + 1e-30)
        delta = 0.5 * (aL - cL) / (aL - 2 * bL + cL)
    else:
        delta = 0.0

    f_b = f_start + (m_max + delta) * (f_end - f_start) / M
    R = f_b * p.dR_dfb
    return R, f_b, S_czt


def estimate_phase(
    s: NDArray, p: FMCWParams, f_b: float, R_coarse: float
) -> tuple[float, float, int]:
    """步骤 3：相位评估 + 整周解模糊 → 最终精距离

    DTFT 在已知 f_b 一点取相位 (无 bias，零 leakage)：
        φ̂ = arg( Σ s[n] · exp(-j·2π·f_b·n/fs) )

    相位每 2π 对应 R 走过 λ_med/2，用粗距离决定整数 k：
        R_phase_raw = φ̂ · c / (4π·f₀·n)        ∈ [-λ_med/4, λ_med/4]
        k = round( (R_coarse - R_phase_raw) / (λ_med/2) )
        R_final = R_phase_raw + k · λ_med/2

    返回 (R_final, phi_est, k)
    """
    N = len(s)
    n = np.arange(N)
    # 对 chirp 中心去相位 (减小数值动态范围) — 等价的，但更稳
    twiddle = np.exp(-1j * 2 * math.pi * f_b * n / p.f_s)
    z = np.sum(s * twiddle)
    phi = math.atan2(z.imag, z.real)

    R_phase_raw = phi * p.dR_dphi
    lam_2 = p.lam_med / 2
    k = round((R_coarse - R_phase_raw) / lam_2)
    R_final = R_phase_raw + k * lam_2
    return R_final, phi, k


def estimate_all(
    s: NDArray, p: FMCWParams
) -> dict:
    """组合流水线：FFT → CZT → Phase"""
    R_fft, fb_fft = estimate_fft(s, p)
    R_czt, fb_czt, _ = estimate_czt(s, p, fb_fft)
    R_phase, phi, k = estimate_phase(s, p, fb_czt, R_czt)
    return {
        "R_fft": R_fft, "fb_fft": fb_fft,
        "R_czt": R_czt, "fb_czt": fb_czt,
        "R_phase": R_phase, "phi": phi, "k": k,
    }


# ============================================================================
# 5. 双反射基准扩展 (我们的工程方案 — 论文之外的扩展)
# ============================================================================
def _estimate_local(
    s: NDArray, p: FMCWParams, R_hint: float, span_m: float | None = None,
) -> tuple[float, float]:
    """在 R_hint 附近 ±span_m 范围内用 CZT 精搜，返回 (R_est, f_b_est)。

    用于三反射场景：每个反射的大致位置 (R_hint) 由机械先验给出，
    避开 FFT bin 分辨率不够的问题。
    span_m 默认 = max(20 mm, 15% × R_hint)，对远目标自动放宽窗口。
    """
    if span_m is None:
        span_m = max(0.020, 0.15 * abs(R_hint))
    fb_hint = R_hint / p.dR_dfb
    f_span = span_m / p.dR_dfb
    N = len(s)
    win = np.hanning(N)

    M = 4096
    f_start = max(fb_hint - f_span / 2, 0.0)
    f_end = fb_hint + f_span / 2
    a = np.exp(1j * 2 * math.pi * f_start / p.f_s)
    w = np.exp(-1j * 2 * math.pi * (f_end - f_start) / (M * p.f_s))
    S = scipy_czt(s * win, m=M, w=w, a=a)
    m_max = int(np.argmax(np.abs(S)))
    if 0 < m_max < M - 1:
        aL = math.log(abs(S[m_max - 1]) + 1e-30)
        bL = math.log(abs(S[m_max]) + 1e-30)
        cL = math.log(abs(S[m_max + 1]) + 1e-30)
        delta = 0.5 * (aL - cL) / (aL - 2 * bL + cL)
    else:
        delta = 0.0
    fb = f_start + (m_max + delta) * (f_end - f_start) / M
    return fb * p.dR_dfb, fb


def estimate_with_reference(
    s: NDArray, p: FMCWParams, L_ref: float, R_target_hint: float,
    R1_hint: float = 0.005, R2_hint: float | None = None,
) -> dict:
    """
    自含基准探针：探针内置两个固定反射点 (相距 L_ref)，活塞为第三反射。
    通过比值法消除油 n 漂移：

        d_radar_i = R_i · (n_live / n_assumed)  (i = 1, 2, 3)
        n_live / n_assumed = (d_radar_2 − d_radar_1) / L_ref
        R_target_real = (d_radar_3 − d_radar_1) / (n_live / n_assumed)

    每个反射用 CZT 在机械先验位置附近精搜，避开多目标 FFT 分辨率问题。
    """
    if R2_hint is None:
        R2_hint = R1_hint + L_ref
    R1_radar, _ = _estimate_local(s, p, R_hint=R1_hint)          # 探针根部
    R2_radar, _ = _estimate_local(s, p, R_hint=R2_hint)          # 探针肩部
    R3_radar, _ = _estimate_local(s, p, R_hint=R_target_hint)    # 活塞

    delta_R_radar = R2_radar - R1_radar
    n_ratio = delta_R_radar / L_ref          # = n_live / n_assumed
    n_live = p.n_oil * n_ratio

    R_target_corrected = (R3_radar - R1_radar) / n_ratio

    return {
        "R1_radar": R1_radar,
        "R2_radar": R2_radar,
        "R3_radar": R3_radar,
        "delta_R_radar": delta_R_radar,
        "L_ref": L_ref,
        "n_ratio": n_ratio,
        "n_live": n_live,
        "n_assumed": p.n_oil,
        "R_target_corrected": R_target_corrected,
    }


# ============================================================================
# 6. Monte-Carlo 性能验证 (单目标，对照 CRB)
# ============================================================================
def monte_carlo(
    R_true: float = 1.234567,
    snr_db_list: list = None,
    n_trials: int = 200,
    p: FMCWParams = None,
    phase_noise_dbc_hz: float = -200.0,
    chirp_nonlin_ppm: float = 0.0,
    seed_base: int = 0,
) -> dict:
    """对每个 SNR 做 n_trials 次实验，统计三种估计的 RMSE。"""
    if snr_db_list is None:
        snr_db_list = [0, 10, 20, 30, 40, 50, 60]
    if p is None:
        p = FMCWParams()

    methods = ["fft", "czt", "phase"]
    results = {m: {"rmse": [], "bias": []} for m in methods}
    crb1_list, crb2_list = [], []

    for snr_db in snr_db_list:
        errs = {m: [] for m in methods}
        for trial in range(n_trials):
            s = fmcw_if_signal(
                R_true, p,
                snr_db=snr_db,
                phase_noise_dbc_hz=phase_noise_dbc_hz,
                chirp_nonlin_ppm=chirp_nonlin_ppm,
                seed=seed_base + trial,
            )
            est = estimate_all(s, p)
            errs["fft"].append(est["R_fft"] - R_true)
            errs["czt"].append(est["R_czt"] - R_true)
            errs["phase"].append(est["R_phase"] - R_true)

        for m in methods:
            arr = np.array(errs[m])
            results[m]["rmse"].append(float(np.sqrt(np.mean(arr**2))))
            results[m]["bias"].append(float(np.mean(arr)))

        snr_lin = 10 ** (snr_db / 10)
        crb1_list.append(crb_range_freq_only(snr_lin, p.N, p))
        crb2_list.append(crb_range_joint(snr_lin, p.N, p))

    return {
        "snr_db": snr_db_list,
        "n_trials": n_trials,
        "results": results,
        "crb1": crb1_list,
        "crb2": crb2_list,
        "params": p,
        "R_true": R_true,
    }


# ============================================================================
# 7. 输出工具
# ============================================================================
def print_params_summary(p: FMCWParams) -> None:
    print("─" * 72)
    print("FMCW 系统参数")
    print("─" * 72)
    print(f"  f₀                  = {p.f0/1e9:>8.3f} GHz")
    print(f"  B                   = {p.B/1e6:>8.1f} MHz")
    print(f"  T_chirp             = {p.T*1e6:>8.1f} µs")
    print(f"  f_s (IF)            = {p.f_s/1e6:>8.2f} MS/s")
    print(f"  N (sample/chirp)    = {p.N:>8d}")
    print(f"  λ₀ (in vacuum)      = {p.lam0*1e3:>8.3f} mm")
    print(f"  λ_oil (n={p.n_oil})  = {p.lam_med*1e3:>8.3f} mm")
    print(f"  距离分辨率 (FFT)    = {p.range_resolution*1e3:>8.2f} mm")
    print(f"  dR/df_b             = {p.dR_dfb*1e9:>8.2f} nm/Hz")
    print(f"  dR/dφ               = {p.dR_dphi*1e6:>8.2f} µm/rad")


def print_crb_table(p: FMCWParams) -> None:
    print("─" * 72)
    print("Cramér-Rao 下界 (单 chirp, AWGN only)")
    print("─" * 72)
    print(f"{'SNR (dB)':>10} {'CRB₁ freq-only':>20} {'CRB₂ joint':>20}")
    for snr_db in [0, 10, 20, 30, 40, 50, 60]:
        snr_lin = 10 ** (snr_db / 10)
        c1 = crb_range_freq_only(snr_lin, p.N, p)
        c2 = crb_range_joint(snr_lin, p.N, p)
        print(f"{snr_db:>10d} {c1*1e6:>16.3f} µm {c2*1e6:>16.4f} µm")


def print_mc_table(mc: dict) -> None:
    p = mc["params"]
    print("─" * 72)
    print(f"Monte-Carlo: R_true = {mc['R_true']*1e3:.3f} mm,  "
          f"trials per SNR = {mc['n_trials']}")
    print("─" * 72)
    hdr = (f"{'SNR':>5} {'CRB₁':>10} {'CRB₂':>10} "
           f"{'σ_FFT':>10} {'σ_CZT':>10} {'σ_Phase':>10}  units: µm")
    print(hdr)
    for i, snr in enumerate(mc["snr_db"]):
        r = mc["results"]
        print(f"{snr:>5d} "
              f"{mc['crb1'][i]*1e6:>10.3f} {mc['crb2'][i]*1e6:>10.3f} "
              f"{r['fft']['rmse'][i]*1e6:>10.3f} "
              f"{r['czt']['rmse'][i]*1e6:>10.3f} "
              f"{r['phase']['rmse'][i]*1e6:>10.3f}")


def print_dual_ref_demo() -> None:
    """演示双反射基准如何在 n_oil 漂移情况下保持目标距离精度。

    对 24 G/250 MHz 系统，FFT bin ≈ 400 mm，简单 FFT+CZT 无法分辨 50 mm
    间距的两基准 — 工程实现需 MUSIC/ESPRIT 等超分辨。本 demo 用 77 GHz
    宽带场景 (B=4 GHz, bin ≈ 25 mm, L_ref=200 mm → 8 bin 间距) 演示原理。
    """
    print("─" * 72)
    print("双反射基准扩展 (我们的方案 — Scherr/Ayhan 之外)")
    print("─" * 72)

    p_demo = FMCWParams(
        f0=77e9, B=4.0e9, T=250e-6, f_s=16e6, n_oil=1.483,
    )
    print(f"  Demo 场景: f₀={p_demo.f0/1e9:.0f} GHz, B={p_demo.B/1e6:.0f} MHz, "
          f"N={p_demo.N}, FFT bin = {p_demo.range_resolution*1e3:.1f} mm")

    L_ref = 0.200       # 200 mm 基准间距 (跨多个 bin)
    R_target_true = 1.500
    n_assumed = p_demo.n_oil
    n_actual_list = [1.420, 1.450, 1.483, 1.510, 1.540]

    print(f"  L_ref = {L_ref*1e3:.0f} mm,  R_target_true = {R_target_true*1e3:.0f} mm")
    print(f"  名义 n = {n_assumed} (出厂标定)")
    print()
    print(f"{'n_real':>8} {'naive 误差':>16} {'比值法残差':>16} {'n_live 估计':>14}")

    for n_real in n_actual_list:
        # 合成三反射混合信号 (真实 n_real 控制相位/频率)
        p_real = FMCWParams(
            f0=p_demo.f0, B=p_demo.B, T=p_demo.T, f_s=p_demo.f_s, n_oil=n_real,
        )
        s_total = np.zeros(p_demo.N, dtype=complex)
        amps = [1.0, 0.6, 0.4]
        # 反射位置：R1 偏移 5 mm 避开 DC，R2 = R1 + L_ref，R3 = 活塞
        R_offset = 0.005
        positions = [R_offset, R_offset + L_ref, R_target_true]
        for amp, R_i in zip(amps, positions):
            s_total += amp * fmcw_if_signal(
                R_i, p_real, snr_db=60.0,
                seed=int((n_real * 1e5 + R_i * 1e6) % 2**31),
            )

        # 真值：活塞相对窗界面 (R1 处) 的物理距离
        R_target_phys = R_target_true - R_offset

        # naive：按名义 n_assumed 直接 CZT 估目标 (不去除 R1 偏移，
        # 因为没有基准；这是工程对照组)
        R_naive, _ = _estimate_local(s_total, p_demo, R_hint=R_target_true)
        err_naive = R_naive - R_target_phys

        # 比值法 (用 p_demo 解释，即按 n_assumed 解距离再做比值修正)
        res = estimate_with_reference(
            s_total, p_demo, L_ref=L_ref, R_target_hint=R_target_true,
            R1_hint=R_offset, R2_hint=R_offset + L_ref,
        )
        err_corrected = res["R_target_corrected"] - R_target_phys
        print(f"{n_real:>8.4f} {err_naive*1e3:>+13.3f} mm "
              f"{err_corrected*1e6:>+13.2f} µm "
              f"{res['n_live']:>14.5f}")


# ============================================================================
# 8. main
# ============================================================================
def main() -> None:
    p = FMCWParams()

    print()
    print("=" * 72)
    print("  Scherr–Ayhan 组合频率+相位估计算法 — 仿真")
    print("=" * 72)

    print_params_summary(p)
    print()
    print_crb_table(p)
    print()

    # ── 主要场景：纯 AWGN，对照三种估计 vs CRB ─────────────────
    print("=" * 72)
    print("  场景 A: 纯 AWGN (无相位噪声 / 无非线性)")
    print("=" * 72)
    mc_a = monte_carlo(
        R_true=1.234567,
        snr_db_list=[0, 10, 20, 30, 40, 50, 60],
        n_trials=200,
        p=p,
    )
    print_mc_table(mc_a)
    print()

    # ── 场景 B：现实的 PLL 相噪 + chirp 非线性 ─────────────────
    print("=" * 72)
    print("  场景 B: PLL 相位噪声 (-85 dBc/Hz @ 1 kHz) + chirp 非线性 (5 ppm)")
    print("=" * 72)
    mc_b = monte_carlo(
        R_true=1.234567,
        snr_db_list=[20, 30, 40, 50, 60],
        n_trials=200,
        p=p,
        phase_noise_dbc_hz=-85.0,
        chirp_nonlin_ppm=5.0,
    )
    print_mc_table(mc_b)
    print()

    # ── 场景 C：双反射基准 demo ─────────────────────────────────
    print("=" * 72)
    print("  场景 C: 双反射基准对 n_oil 漂移的鲁棒性 (我们的扩展)")
    print("=" * 72)
    print_dual_ref_demo()
    print()

    # ── 输出图 (若 matplotlib 可用) ─────────────────────────────
    try:
        _plot_results(mc_a, mc_b, p)
    except Exception as e:
        print(f"(跳过绘图: {e})")


def _plot_results(mc_a: dict, mc_b: dict, p: FMCWParams) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    for ax, mc, title in [
        (axes[0], mc_a, "A: pure AWGN"),
        (axes[1], mc_b, "B: PLL phase noise + 5 ppm chirp nonlinearity"),
    ]:
        snr = mc["snr_db"]
        ax.plot(snr, [c * 1e6 for c in mc["crb1"]], "k--", lw=1.5,
                label="CRB$_1$ (freq only)")
        ax.plot(snr, [c * 1e6 for c in mc["crb2"]], "k:", lw=1.5,
                label="CRB$_2$ (joint)")
        ax.plot(snr, [v * 1e6 for v in mc["results"]["fft"]["rmse"]], "o-",
                label="FFT only")
        ax.plot(snr, [v * 1e6 for v in mc["results"]["czt"]["rmse"]], "s-",
                label="FFT + CZT")
        ax.plot(snr, [v * 1e6 for v in mc["results"]["phase"]["rmse"]], "^-",
                label="FFT + CZT + Phase")
        ax.set_yscale("log")
        ax.set_xlabel("SNR (dB)")
        ax.set_ylabel("range RMSE (µm)")
        ax.set_title(title)
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(loc="best", fontsize=8)

    fig.suptitle(
        f"Scherr–Ayhan algorithm (f$_0$={p.f0/1e9:.1f} GHz, B={p.B/1e6:.0f} MHz, "
        f"T={p.T*1e6:.0f} µs, N={p.N}, n={p.n_oil})",
        fontsize=10,
    )
    fig.tight_layout()
    out_path = "scherr_ayhan_sim.png"
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    print(f"图已写入: {out_path}")


if __name__ == "__main__":
    main()
