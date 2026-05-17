# Scherr–Ayhan 组合频率+相位估计算法

> 高精度 FMCW 测距的核心算法，对应 KIT (Karlsruhe Institute of Technology)
> Ayhan 团队 2013–2015 年系列论文。**本文档同时是该算法在我们 IRM 液压
> 缸位置传感器项目上的实现说明 + 双反射基准扩展的推导**。
> 配套可运行仿真见 [`scherr_ayhan_sim.py`](./scherr_ayhan_sim.py)。

---

## 1. 算法来源

| 出处 | 主要贡献 |
|---|---|
| Ayhan et al., **"High-Accuracy Range Detection Radar Sensor for Hydraulic Cylinders,"** IEEE TMTT 62(3), 2014 | 油充波导液压缸雷达系统级实现，5 µm 精度演示 |
| Scherr et al., **"An Efficient Frequency and Phase Estimation Algorithm With CRB Performance for FMCW Radar Applications,"** IEEE TIM 64(7), 2015 | 算法本体，CZT + 相位评估，CRB 分析 |
| Ayhan et al., "FMCW Radar System with Additional Phase Evaluation for High Accuracy Range Detection," EuMA 2011 | 最初的"附加相位评估"思想 |
| Scherr & Ayhan, "Accuracy Limits of a K-band FMCW Radar with Phase Evaluation," EuRAD 2012 | CRB 极限分析，硬件预算 |

## 2. 核心思想

FMCW 雷达的中频信号同时携带两份关于目标距离 R 的信息，敏感度差 5 个数量级：

| 信号特征 | 表达式 | 距离敏感度 (R) | 模糊性 |
|---|---|---|---|
| **差拍频率** f_b | 2·B·n·R / (c·T) | dR/df_b ≈ **10⁻⁷ m/Hz** | 无（绝对） |
| **载频相位** φ₀ | 4π·f₀·n·R / c | dR/dφ ≈ **10⁻³ m/rad** | 每 2π 重复 (λ_med/2) |

**核心思想**：用频率定粗位置（百 µm-mm 级），再用相位精测 sub-µm 残差。
相位的高精度由"载频 f₀ ≫ 带宽 B"这一物理事实保证：在 24 GHz / 250 MHz
系统中，f₀ / B = 96，意味着相位测同样的距离比频率灵敏 96 倍。

这对应估计理论的两条 Cramér–Rao 下界：

- **CRB₁ (phase unknown)**：只用频率信息估 R，精度由 c/B 限制
- **CRB₂ (phase known)**：用频率+相位联合估 R，精度由 c/f₀ 限制

CRB₂ / CRB₁ ≈ B / f₀ ≈ 1 %，即两个数量级精度提升。

---

## 3. 信号模型

### 3.1 发射 chirp

$$
f_{TX}(t) = f_0 - \tfrac{B}{2} + \frac{B}{T}\,t, \quad t \in [0, T]
$$

瞬时相位：

$$
\phi_{TX}(t) = 2\pi \int_0^t f_{TX}(\tau)\,d\tau
            = 2\pi\Big(f_0 - \tfrac{B}{2}\Big) t + \pi\frac{B}{T}\,t^2
$$

### 3.2 单目标回波 (距离 R, 油折射率 n)

光经油介质往返时间：

$$
\tau = \frac{2 R n}{c}
$$

接收端信号 = TX 在 t-τ 时刻的形式，与 LO 混频后得 IF 信号（基带，复数形式）：

$$
s_{IF}(t) = A \cdot \exp\!\Big[\,j\big(2\pi f_b\, t + \varphi_0\big)\,\Big] + w(t)
$$

其中两个关键参数：

$$
\boxed{\;f_b = \frac{2 B n R}{c\,T}\;} \qquad \boxed{\;\varphi_0 = \frac{4\pi f_0\, n\, R}{c}\;}
$$

> 推导提示：忽略二阶 t² 项后，IF 相位 = φ_TX(t) − φ_TX(t−τ) ≈ (dφ/dt)·τ +
> (1/2)·(d²φ/dt²)·τ²·t。第一项给出 f_b·t，第二项给出 φ₀（载频对 τ 的相位
> 累积）。完整推导见 Scherr 2015 §II.A。

### 3.3 采样

ADC 以 f_s 采 IF 信号，每 chirp 取 N = T·f_s 个复样本：

$$
s[n] = A \exp\!\Big[\,j\,\big(\omega n + \varphi_0\big)\,\Big] + w[n],\quad
\omega = \frac{2\pi f_b}{f_s}
$$

ω 与 φ₀ 均为 R 的线性函数：

$$
\omega = \alpha R, \quad \alpha = \frac{4\pi B n}{c T f_s}
\;\;[\text{rad/sample/m}]
$$

$$
\varphi_0 = \beta R, \quad \beta = \frac{4\pi f_0 n}{c}
\;\;[\text{rad/m}]
$$

对于我们的 24 GHz / 250 MHz / T=250 µs / f_s=2 MS/s / n=1.483 设置：

| 量 | 值 |
|---|---|
| α | 6.21 × 10⁻⁵ rad/sample/m |
| β | 1494 rad/m |
| **β / (α N)** ≈ f₀·T·f_s / (B·N) | **96** |

β 主导（即相位敏感度），是 CRB₂ ≪ CRB₁ 的根源。

---

## 4. Cramér–Rao 下界推导

### 4.1 Fisher 信息

对 R 的对数似然函数梯度：

$$
\frac{\partial \ln L}{\partial R}
= -\frac{2}{\sigma^2}\,\text{Im}\!\Big\{
\sum_n (s[n]-\hat s[n])^*\,\big(j(\alpha n + \beta)\big)\hat s[n]
\Big\}
$$

Fisher 信息（复正弦在 AWGN 中）：

$$
I(R) = \frac{2 A^2}{\sigma^2} \sum_{n=0}^{N-1} (\alpha n + \beta)^2
     = 2\cdot \text{SNR}\,\Big[\,\alpha^2 \tfrac{N(N-1)(2N-1)}{6}
     + \alpha\beta\, N(N-1) + \beta^2 N\Big]
$$

### 4.2 两条 CRB

**CRB₁ (phase unknown)** — 只用频率，β 项失效：

$$
\boxed{\;\sigma_R^{(1)} \ge \frac{1}{\alpha}\sqrt{\frac{12}{\text{SNR}\cdot N(N^2-1)}}\;}
\;\;\propto\;\frac{1}{\sqrt{\text{SNR}}}\,\frac{c T f_s}{4\pi B n N^{3/2}}
$$

代入 24 G/250 M/N=500/SNR=30 dB：σ_R⁽¹⁾ ≈ **316 µm**

**CRB₂ (joint)** — 频率+相位都用，β² 项主导：

$$
\sigma_R^{(2)} \ge \frac{1}{\sqrt{I(R)}} \;\;\approx\;
\frac{1}{\beta\sqrt{2\,\text{SNR}\cdot N}}
\;=\;\boxed{\;\frac{c}{4\pi f_0 n}\,\frac{1}{\sqrt{2\,\text{SNR}\cdot N}}\;}
$$

代入同参数：σ_R⁽²⁾ ≈ **0.66 µm** — 比 CRB₁ 紧 **480 倍**。

```
                 ┌──── 24 GHz / 250 MHz / N=500 / SNR=30dB
                 │
  CRB₁ (freq):   ├───────► 316 µm   ← 只用频率
                 │
  CRB₂ (joint):  ├► 0.66 µm         ← 加相位评估
                 │
        实测 (Scherr 2015):
                 ├► 0.77 µm (mean std)
                 │
        我们仿真 (本仓库, AWGN only):
                 ├► 1.65 µm @ 30 dB SNR
```

---

## 5. 三步估计算法

```
        s_IF[n]
           │
           ▼
   ┌───────────────┐     R_coarse   (~mm 精度)
   │  ①  FFT       ├─► f_b_coarse
   │   N pts       │     -- 解 R 整 bin 模糊
   │   Hann 窗     │
   │   抛物线插值  │
   └───────┬───────┘
           │ f_b_coarse
           ▼
   ┌───────────────┐     R_fine     (~10 µm 精度, 趋近 CRB₁)
   │  ② CZT        ├─► f_b_fine
   │  M=1024 pts   │     -- bin 内细搜
   │  ±2 bin 窗    │
   └───────┬───────┘
           │ f_b_fine
           ▼
   ┌───────────────┐     R_final    (~ µm 精度, 趋近 CRB₂)
   │  ③ Phase      │
   │  DTFT @ f_b   ├─► R_final
   │  整周解模糊   │     -- 用 R_fine 决定 k ∈ ℤ
   │  R + k·λ/2    │
   └───────────────┘
```

### 5.1 第一步：FFT + 抛物线插值 (粗距离)

```python
S = FFT(Hann(s))                           # N 点 FFT
k_max = argmax |S[0:N/2]|                  # 找正频率主峰
δ = 0.5·(log|S_{k-1}| - log|S_{k+1}|) /
       (log|S_{k-1}| - 2 log|S_k| + log|S_{k+1}|)
f̂_b_coarse = (k_max + δ) · f_s / N
R̂_coarse  = f̂_b_coarse · c·T / (2·B·n)
```

- **窗函数**：Hann 减泄漏，主瓣 ≈ 4 bin，旁瓣 −31 dB
- **抛物线插值 (log-amplitude)**：Jacobsen 类方法，bin 内 1% 精度
- 在 N=500 / Hann / 30 dB SNR 下，FFT 步骤 RMSE ~1–2 mm（受插值偏差限制）

### 5.2 第二步：CZT 精频率估计

**Chirp-Z Transform** 在 z 平面上沿任意螺线/圆弧均匀取 M 个点：

$$
X_{CZT}[m] = \sum_{n=0}^{N-1} x[n]\,A^{-n}\,W^{m n},\quad m = 0,\dots,M-1
$$

参数选择以扫描 `[f_start, f_end]` 频段内 M 点：

$$
A = e^{\,j 2\pi f_{start}/f_s},\quad
W = e^{-j 2\pi (f_{end}-f_{start})/(M\,f_s)}
$$

**Bluestein 算法** 把 CZT 化为三步：

1. 预乘 `x[n] · A⁻ⁿ · W^{n²/2}`
2. 用长度 ≥ N+M−1 的 FFT 做循环卷积 (与 W^{−n²/2} 卷积)
3. 后乘 `W^{m²/2}`

复杂度 O((N+M) log(N+M))，FPGA 友好。我们用 M=1024 在 FFT 主峰 ±2 bin 内
做精细扫描，等效在主峰附近做 4096 倍 zero-padding，远高效于直接 zero-padded
FFT。

CZT 输出峰位再做一次抛物线插值：

$$
\hat f_b = f_{start} + (m_{\max} + \delta_{CZT}) \cdot \frac{f_{end}-f_{start}}{M}
$$

**精度**：仿真显示 CZT 在 SNR ≥ 30 dB 时 RMSE 紧贴 CRB₁（300 µm），证明
频率信息已充分利用。

### 5.3 第三步：相位评估 + 解模糊 (核心)

**相位估计** = 在已知频率 f̂_b 处取 DTFT 辐角，无谱泄漏、无 bias：

$$
\boxed{\;\hat\varphi = \arg\!\Big(\sum_{n=0}^{N-1} s[n]\,e^{-j 2\pi \hat f_b\, n / f_s}\Big)\;}
$$

等价地用 CZT 输出在峰位的复数辐角：

$$
\hat\varphi = \arg\!\big(X_{CZT}[m_{\max}]\big)
$$

两者一致；后者免一次乘累加，但前者数值动态范围更稳。

**整周解模糊**：相位每 2π 对应 R 走过 λ_med/2 = c/(2 f₀ n) ≈ **4.19 mm**：

$$
R_{\text{phase\_raw}} = \hat\varphi \cdot \frac{c}{4\pi f_0 n} \in [-\lambda_{med}/4,\,\lambda_{med}/4]
$$

用 CZT 给的 R̂_fine 决定整数 k：

$$
k = \mathrm{round}\!\left(\frac{R_{\text{fine}} - R_{\text{phase\_raw}}}{\lambda_{med}/2}\right)
$$

最终精距离：

$$
\boxed{\;R_{\text{final}} = R_{\text{phase\_raw}} + k\cdot\frac{\lambda_{med}}{2}\;}
$$

**解模糊条件**：σ(R_fine) < λ_med / 4 ≈ 1 mm。CRB₁ 在 SNR ≥ 30 dB 时
~300 µm，远小于此阈值，**几乎不会跳周**。SNR < 10 dB 时跳周概率上升，
工程上要做 SNR 监测 + 多 chirp 投票。

---

## 6. 实测性能 (Scherr/Ayhan 2014)

KIT 团队在自制 1 m 油充液压缸上测量结果：

| 参数 | 值 |
|---|---|
| 载频 f₀ | 24 GHz (K-band ISM 24.0–24.25 GHz) |
| 带宽 B | 250 MHz |
| Chirp 周期 T | 1 ms |
| ADC | 12-bit @ 5 MS/s |
| 范围 | 0.1 – 3 m (油充圆波导) |
| **平均标准差 σ_R** | **774 nm** |
| 最大误差 (vs 光栅尺) | 5 µm |
| 理论 CRB₂ | 160 nm |
| 与 CRB₂ 差距 | 4.8× (实测/理论) |

实测距 CRB₂ 还有 5× 余量，主要来自：

- PLL 相位噪声 (~ −90 dBc/Hz @ 1 kHz, 累积 ~1 mrad RMS)
- ADC 量化 (12-bit / 72 dB SNR 上限)
- Chirp 非线性 (~ 几 ppm，主峰展宽)
- 多模反射残余

> 这些限制在我们仿真的"场景 B"中复现：当 PLL 相噪开启后，相位 RMSE
> 在 0.4–0.5 µm 饱和，与 KIT 报告一致。

---

## 7. 我们的实现位置

| 子系统 | 位置 | 实现说明 |
|---|---|---|
| FFT + Hann | STM32H743 ART-fft DMA | 1024 点定点 (Q15) |
| 抛物线插值 | F743 主算法循环 | 浮点 |
| CZT | 同上, M=1024 | Bluestein, 3× FFT(1024) |
| 相位估计 | 同上 | 单点 DTFT (sin/cos LUT 1024 项) |
| 解模糊 | 同上 | round + 历史平滑 |
| Kalman 平滑 | 同上 | [pos, vel] 状态 |
| 实时性 | 1.5 ms / 帧 | 满足 1 kHz 上送 |

固件代码骨架将放在 `firmware/algo/` (P4 阶段)。

---

## 8. 我们的扩展：双反射基准比值法

### 8.1 动机

Scherr/Ayhan 论文假设 ε_r (油折射率 n) 已知。但在液压缸里：

- 温度 −40 ～ +105 °C 让 ε_r 变化 ±2%
- 压力 0 ～ 350 bar 让 ε_r 变化 ~0.5%
- 油品老化、油品互换让 ε_r 变化 ±5%

绝对精度 100 µm @ 2 m (50 ppm) 要求 ε_r 知道到 ~25 ppm，**仅靠出厂标定
+ 温度补偿做不到**。

### 8.2 方案

在传感器探针内置两个固定反射点 R₁, R₂，间距 L_ref（机械精密件，
super-Invar 棒）。活塞为第三反射 R₃。雷达"看到"的所有距离都按
名义 n 解释：

$$
d_{radar,i} = R_i\cdot\frac{n_{live}}{n_{assumed}}, \quad i = 1, 2, 3
$$

R₂ − R₁ 的"雷达距离"消去 R₁ 偏移，只留下 L_ref：

$$
d_{radar,2} - d_{radar,1} = L_{ref}\cdot\frac{n_{live}}{n_{assumed}}
$$

得 **n_live 的实时估计**：

$$
\boxed{\;\frac{n_{live}}{n_{assumed}} = \frac{d_{radar,2} - d_{radar,1}}{L_{ref}}\;}
$$

代回 R₃，**消除 ε_r 全部影响**：

$$
\boxed{\;R_{target} = \frac{d_{radar,3} - d_{radar,1}}{(d_{radar,2} - d_{radar,1})/L_{ref}}\;}
$$

### 8.3 误差预算

| 误差源 | 贡献 |
|---|---|
| L_ref 加工公差 (±5 µm out of 50 mm) | 100 ppm → 200 µm @ 2 m |
| L_ref 热漂 (super-Invar, 0.5 ppm/K × 145 K) | 73 ppm → 146 µm @ 2 m 未补偿 |
| L_ref 温补残差 (PT1000 + ε_r(T) LUT) | < 10 ppm → 20 µm @ 2 m |
| R₁ 测量噪声 (CRB₂ @ 30 dB SNR) | 0.66 µm |
| R₂ 测量噪声 | 0.66 µm |
| R₃ 测量噪声 | 0.66 µm |
| **合成 (RSS, T 全程)** | **~30 µm @ 2 m** |

满足绝对 ±100 µm 指标。重复性受 R 测量噪声主导，~2 µm。

### 8.4 三反射分离

简单 FFT + CZT 在 24 GHz / 250 MHz / 50 mm L_ref 上分不开反射（bin 宽
400 mm）。工程上选其中之一：

| 方法 | 备注 |
|---|---|
| **拉大 L_ref → 500 mm** | 折损死区 |
| **超分辨 (MUSIC / Matrix Pencil)** | 算力 ↑, 分辨能力 ↓ 几 bin |
| **多 chirp 联合 + 模型拟合** | 已知反射近似位置作约束 |
| **77 GHz 宽带 (B=2-4 GHz)** | bin 宽 ≤ 25 mm，直接分辨 |

仿真 (`scherr_ayhan_sim.py` 场景 C) 用 77 GHz / 4 GHz BW 作概念演示，
ε_r 漂移 ±4% 时残差 < 0.3 mm，n_live 估到 1e-4 精度。

---

## 9. 边界条件与失败模式

| 场景 | 现象 | 对策 |
|---|---|---|
| SNR < 10 dB | 相位整周解模糊跳变 | 多 chirp 投票 + R̂ Kalman 平滑 |
| 多目标干涉 (探针窗 + 活塞) | FFT 主峰带肩 | 模板减除已知近端反射 |
| 大速度活塞 (Doppler) | f_b 与 f_phase 时变 | 上下 chirp 平均消多普勒 |
| Chirp 严重非线性 (>50 ppm) | f_b 散播多 bin | DDS 预失真 + 出厂线性度标定 |
| PLL 相噪 > −80 dBc/Hz | σ_R 底大于 5 µm | 提升 VCO 选型 / 加 OCXO 参考 |
| 油气泡 (空化) | 部分反射 / 非高斯噪声 | 多 chirp 中值滤波 |

---

## 10. 关键公式速查

```
信号:        s[n] = A·exp[j(2π·f_b·n/fs + φ_0)] + 噪声

  f_b      = 2·B·n·R / (c·T)
  φ_0      = 4π·f_0·n·R / c
  λ_med    = c / (f_0·n)         (油中波长)

CRB:
  σ_R⁽¹⁾   ≈ (cTf_s)/(4πBnN^1.5) · √(12/SNR)        ← phase unknown
  σ_R⁽²⁾   ≈ c/(4πf_0·n) · 1/√(2·SNR·N)              ← phase known

算法:
  ① k_max  = argmax|FFT(s·win)|
     f̂_b_coarse + 抛物线插值
  ② CZT 在 [f̂_b - 2/T, f̂_b + 2/T] 取 M=1024 点
     f̂_b_fine = max + 抛物线插值
  ③ φ̂      = arg(Σ s[n]·exp(-j2π f̂_b·n/fs))
     R_raw  = φ̂ · c/(4π·f_0·n)
     k      = round((R_fine - R_raw) / (λ_med/2))
     R_final= R_raw + k·λ_med/2

我们的扩展 (n_oil 自标定):
  n_live/n_assumed = (R̂_2 - R̂_1)/L_ref
  R_target_corrected = (R̂_3 - R̂_1) · L_ref/(R̂_2 - R̂_1)
```

---

## 11. 参考与延伸阅读

1. **S. Ayhan et al.**, "High-Accuracy Range Detection Radar Sensor for Hydraulic Cylinders," *IEEE Trans. Microwave Theory Tech.*, vol. 62, no. 3, pp. 572–581, Mar. 2014. DOI: 10.1109/TMTT.2013.2293866
2. **S. Scherr et al.**, "An Efficient Frequency and Phase Estimation Algorithm With CRB Performance for FMCW Radar Applications," *IEEE Trans. Instrum. Meas.*, vol. 64, no. 7, pp. 1868–1875, Jul. 2015. DOI: 10.1109/TIM.2015.2381958
3. **D. C. Rife and R. R. Boorstyn**, "Single-tone parameter estimation from discrete-time observations," *IEEE Trans. Inf. Theory*, vol. IT-20, no. 5, pp. 591–598, Sep. 1974. — CRB 经典推导
4. **L. R. Rabiner, R. W. Schafer, and C. M. Rader**, "The chirp z-transform algorithm," *IEEE Trans. Audio Electroacoust.*, vol. AU-17, no. 2, pp. 86–92, Jun. 1969. — Bluestein 算法
5. **E. Jacobsen and P. Kootsookos**, "Fast, accurate frequency estimators," *IEEE Signal Process. Mag.*, vol. 24, no. 3, pp. 123–125, May 2007. — 插值方法
6. **S. Ayhan, T. Zwick**, "FMCW Radar in Oil-Filled Waveguides for Range Detection in Hydraulic Cylinders," GeMiC 2014. — 油波导细节
7. 本仓库 [`scherr_ayhan_sim.py`](./scherr_ayhan_sim.py) — 可运行的 Python 仿真，复现本文所有公式
8. 本仓库 [`../00-overview/01-plan.md`](../00-overview/01-plan.md) §5 — 算法栈在系统中的位置
9. 本仓库 [`../01-link-budget/24ghz-link-budget.md`](../01-link-budget/24ghz-link-budget.md) — SNR 预算（CRB 输入）
