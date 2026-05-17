// ============================================================
// File   : FB_PlantSim.st
// 用途   : 单缸液压伺服系统离散仿真模型(仅用于ILC算法验证)
//          模型: G(s) = K·exp(-Td·s) / (Tv·s + 1) → 积分器
//          阀:一阶滞后 + 纯延迟
//          缸:积分(速度→位置)
// 离散化: 显式欧拉 + 循环缓冲实现纯延迟
// ============================================================

FUNCTION_BLOCK FB_PlantSim
VAR CONSTANT
    MAX_DELAY_BUF : INT := 64;     // 最大支持64样本纯延迟
END_VAR
VAR_INPUT
    rValveCmd     : REAL;          // 阀指令 (-1.0 ~ +1.0 归一化)
    rTs           : REAL := 0.001; // 采样周期 (s)
    rValveTC      : REAL := 0.010; // 阀时间常数 (s)
    rPureDelay_s  : REAL := 0.005; // 纯延迟 (s)
    rGain         : REAL := 100.0; // 流量增益 (mm/s per unit cmd)
    rPosMax       : REAL := 300.0;
    rPosMin       : REAL := 0.0;
    rPosInit      : REAL := 100.0; // 初始位置
    rViscousFric  : REAL := 0.05;  // 粘滞摩擦(模拟非线性)
    bReset        : BOOL := FALSE;
END_VAR
VAR_OUTPUT
    rPosOut       : REAL;
    rVelOut       : REAL;
END_VAR
VAR
    rDelayBuf     : ARRAY[0..63] OF REAL;
    iDelayIdx     : INT;
    iDelaySamples : INT;
    rValveState   : REAL;          // 阀一阶滞后内部状态
    rAlphaLag     : REAL;
    rDelayedCmd   : REAL;
    bInit         : BOOL := FALSE;
END_VAR

IF NOT bInit OR bReset THEN
    iDelaySamples := REAL_TO_INT(rPureDelay_s / rTs);
    IF iDelaySamples >= MAX_DELAY_BUF THEN iDelaySamples := MAX_DELAY_BUF - 1; END_IF
    IF iDelaySamples < 0 THEN iDelaySamples := 0; END_IF
    IF (rValveTC + rTs) > 1.0E-9 THEN
        rAlphaLag := rTs / (rValveTC + rTs);
    ELSE
        rAlphaLag := 1.0;
    END_IF
    iDelayIdx := 0;
    rValveState := 0.0;
    rPosOut := rPosInit;
    rVelOut := 0.0;
    FOR iDelayIdx := 0 TO MAX_DELAY_BUF - 1 DO
        rDelayBuf[iDelayIdx] := 0.0;
    END_FOR
    iDelayIdx := 0;
    bInit := TRUE;
END_IF

// 1. 纯延迟:循环缓冲
rDelayedCmd := rDelayBuf[iDelayIdx];
rDelayBuf[iDelayIdx] := rValveCmd;
iDelayIdx := iDelayIdx + 1;
IF iDelayIdx > iDelaySamples THEN iDelayIdx := 0; END_IF

// 2. 阀一阶滞后:rValveState ← (1-α)·old + α·newCmd
rValveState := rValveState + rAlphaLag * (rDelayedCmd - rValveState);

// 3. 流量→速度,引入粘滞摩擦
rVelOut := rValveState * rGain - rViscousFric * rVelOut;

// 4. 速度→位置 (显式欧拉积分)
rPosOut := rPosOut + rVelOut * rTs;

// 5. 位置限幅
IF rPosOut > rPosMax THEN
    rPosOut := rPosMax;
    IF rVelOut > 0.0 THEN rVelOut := 0.0; END_IF
END_IF
IF rPosOut < rPosMin THEN
    rPosOut := rPosMin;
    IF rVelOut < 0.0 THEN rVelOut := 0.0; END_IF
END_IF

END_FUNCTION_BLOCK
