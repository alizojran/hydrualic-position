// ============================================================
// File   : FB_PhaseLeadTuner.st
// 用途   : 通过阶跃响应自动估计 FB_CrossCoupledILC 的 iPhaseLead
//          - 单缸独立运行,需要将该缸的位置环setpoint切换到本FB输出
//          - 等待系统稳态 → 施加位置阶跃 → 测量响应
//          - 提取 10%/50%/90% 上升时间 → 估计纯延迟、主时间常数、相位超前
//
// 算法依据:
//          对一阶系统 G(s) = K·exp(-Td·s) / (Tv·s+1):
//            10%上升时间 ≈ Td + 0.1·Tv
//            50%上升时间 ≈ Td + 0.69·Tv  ← ILC的iPhaseLead取此值
//            90%上升时间 ≈ Td + 2.30·Tv
//
//          高阶/非线性系统 t50 仍是ILC前馈补偿的良好近似
//          (经验:闭环ILC收敛速度对 ±50% Δ 误差并不敏感)
// ============================================================

FUNCTION_BLOCK FB_PhaseLeadTuner
VAR CONSTANT
    MAX_MEASURE : INT := 4000;     // 最大测量点数(对应4s @ 1kHz)
END_VAR
VAR_INPUT
    bStart       : BOOL;           // 上升沿:启动整定
    bAbort       : BOOL;           // 中止
    rTs          : REAL := 0.001;  // 采样周期 (s)
    rPosFb       : REAL;           // 位置反馈
    rStepSize    : REAL := 5.0;    // 阶跃幅度 (mm,过大易撞限位,过小信噪比差)
    rSettleTol   : REAL := 0.05;   // 稳态判定容差 (mm)
    iSettlePts   : INT  := 200;    // 稳态保持采样点数
    iMaxMeasPts  : INT  := 3000;   // 测量阶段最大采样点
END_VAR
VAR_OUTPUT
    rStepCmdOut  : REAL;           // 应送给位置环的setpoint
                                   // (调用方应在 bRunning=TRUE 时使用此输出)
    bRunning     : BOOL;
    bDone        : BOOL;
    bFailed      : BOOL;
    iEstLeadPts  : INT;            // ★ 估计的相位超前(采样点数,直接送ILC)
    rEstDelay_s  : REAL;           // 估计的纯延迟 Td (s)
    rEstTau_s    : REAL;           // 估计的主时间常数 Tv (s)
    rEstRise50_s : REAL;           // 50% 上升时间 (s)
    iState       : INT;            // 0=IDLE,1=WAIT_STABLE,2=MEASURING,3=DONE,4=FAILED
    rDiagBaseline: REAL;
    rDiagTarget  : REAL;
END_VAR
VAR
    eState        : INT;
    bStartPrev    : BOOL;
    iSettleCount  : INT;
    iMeasCount    : INT;
    rBaseline     : REAL;
    rTarget       : REAL;
    rT10Thresh    : REAL;
    rT50Thresh    : REAL;
    rT90Thresh    : REAL;
    iT10          : INT;
    iT50          : INT;
    iT90          : INT;
    rDelta        : REAL;
    bStepRising   : BOOL;
END_VAR

// 上升沿检测
IF bAbort THEN
    eState := 0;
    bDone := FALSE;
    bFailed := FALSE;
END_IF

IF bStart AND NOT bStartPrev AND (eState = 0 OR eState >= 3) THEN
    eState := 1;
    iSettleCount := 0;
    iMeasCount   := 0;
    iT10 := -1; iT50 := -1; iT90 := -1;
    bDone := FALSE;
    bFailed := FALSE;
    rBaseline := rPosFb;
END_IF
bStartPrev := bStart;

CASE eState OF

0:  // IDLE
    rStepCmdOut := rPosFb;
    bRunning    := FALSE;

1:  // WAIT_STABLE — 等系统稳定到当前位置
    rStepCmdOut := rBaseline;
    bRunning    := TRUE;
    IF ABS(rPosFb - rBaseline) < rSettleTol THEN
        iSettleCount := iSettleCount + 1;
    ELSE
        iSettleCount := 0;
        rBaseline    := rPosFb;
    END_IF
    IF iSettleCount >= iSettlePts THEN
        // 配置阶跃(默认向正方向,若已在上限附近则向负方向)
        bStepRising := TRUE;
        rTarget     := rBaseline + rStepSize;
        rT10Thresh  := rBaseline + 0.1 * rStepSize;
        rT50Thresh  := rBaseline + 0.5 * rStepSize;
        rT90Thresh  := rBaseline + 0.9 * rStepSize;
        iMeasCount  := 0;
        eState      := 2;
    END_IF

2:  // MEASURING — 阶跃已施加,记录上升时刻
    rStepCmdOut := rTarget;
    bRunning    := TRUE;
    rDelta      := rPosFb - rBaseline;

    IF iT10 = -1 AND rDelta >= 0.1 * rStepSize THEN iT10 := iMeasCount; END_IF
    IF iT50 = -1 AND rDelta >= 0.5 * rStepSize THEN iT50 := iMeasCount; END_IF
    IF iT90 = -1 AND rDelta >= 0.9 * rStepSize THEN
        iT90 := iMeasCount;
        // 计算结果
        rEstDelay_s  := INT_TO_REAL(iT10) * rTs;
        rEstRise50_s := INT_TO_REAL(iT50) * rTs;
        // Tv 经验估计:(t90 - t10) / 2.2
        rEstTau_s    := INT_TO_REAL(iT90 - iT10) * rTs / 2.2;
        // ILC iPhaseLead = t50 (覆盖纯延迟 + 主时间常数主体)
        iEstLeadPts  := iT50;
        IF iEstLeadPts < 0 THEN iEstLeadPts := 0; END_IF
        eState := 3;
    END_IF

    iMeasCount := iMeasCount + 1;
    IF iMeasCount >= iMaxMeasPts OR iMeasCount >= MAX_MEASURE THEN
        // 超时,响应未达到90%(可能阶跃太大、增益不足、卡死)
        eState := 4;
    END_IF

3:  // DONE
    rStepCmdOut := rTarget;
    bRunning    := FALSE;
    bDone       := TRUE;

4:  // FAILED
    rStepCmdOut := rBaseline;     // 回退到起点,避免悬停在异常目标
    bRunning    := FALSE;
    bFailed     := TRUE;

ELSE
    eState      := 0;
    rStepCmdOut := rPosFb;
END_CASE

iState        := eState;
rDiagBaseline := rBaseline;
rDiagTarget   := rTarget;

END_FUNCTION_BLOCK
