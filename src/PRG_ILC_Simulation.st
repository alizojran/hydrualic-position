// ============================================================
// File   : PRG_ILC_Simulation.st
// 用途   : 3缸刚性同步加载场景的纯软件仿真
//          - 三缸故意配置不同的阀时间常数/纯延迟/流量增益
//          - 正弦波目标,1Hz,幅值50mm,中点100mm,1000点/周期
//          - 期望:不开ILC时,缸间同步误差显著;
//                  开ILC后,~10-30周期内收敛
//
// 调用方式: 配置到 CODESYS 1ms 周期任务,在 Simulation 模式下运行
//          在 Online → Watch 窗口监控:
//            aRmsHistory[*]       → 每周期跟踪RMS(应单调递减)
//            aSyncErrHistory[*]   → 每周期最大同步误差
//            fbILC.eState         → 状态机
//            aPosFb[1..3] / aPosCmd[1..3] → 实时位置曲线(可Trend)
// ============================================================

PROGRAM PRG_ILC_Simulation
VAR
    // ---- ILC ----
    fbILC          : FB_CrossCoupledILC;
    aPosCmd        : ARRAY[1..200] OF REAL;
    aVelCmd        : ARRAY[1..200] OF REAL;
    aPosFb         : ARRAY[1..200] OF REAL;
    aSyncRef       : ARRAY[1..200] OF REAL;
    aChEnable      : ARRAY[1..200] OF BOOL;
    aPosCmdOut     : ARRAY[1..200] OF REAL;

    // ---- PID + 仿真被控对象 (3缸)----
    fbPID          : ARRAY[1..3] OF FB_SimplePID;
    fbPlant        : ARRAY[1..3] OF FB_PlantSim;
    aValveCmd      : ARRAY[1..3] OF REAL;

    // ---- 波形生成 ----
    rTs            : REAL := 0.001;     // 1ms采样
    rFreq          : REAL := 1.0;       // 1Hz脉冲
    rAmp           : REAL := 50.0;      // 幅值50mm
    rOffset        : REAL := 100.0;     // 中点100mm
    rPhaseRad      : REAL;
    rTwoPi         : REAL := 6.283185307;
    iPointsPerCycle: INT  := 1000;
    iPhaseIdx      : INT;
    bNewCycle      : BOOL;
    bNewCyclePrev  : BOOL;
    bCycleEdge     : BOOL;

    // ---- 收敛监控 ----
    aRmsHistory    : ARRAY[0..99] OF REAL;    // 跟踪RMS历史
    aSyncErrHistory: ARRAY[0..99] OF REAL;    // 同步误差峰值历史
    aPeakErrHistory: ARRAY[0..99] OF REAL;    // 跟踪峰值历史
    iCycleLog      : INT;
    iCycleCount    : INT;

    // ---- 控制开关 ----
    bEnableILC     : BOOL := TRUE;
    bResetSim      : BOOL := FALSE;

    // ---- 内部 ----
    bInit          : BOOL := FALSE;
    i              : INT;
END_VAR

// ============================================================
// 初始化(只跑一次)
// ============================================================
IF NOT bInit OR bResetSim THEN
    FOR i := 1 TO 3 DO aChEnable[i] := TRUE; END_FOR
    FOR i := 4 TO 200 DO aChEnable[i] := FALSE; END_FOR

    // 三缸故意配置不同参数(模拟制造公差)
    fbPlant[1].rValveTC      := 0.010;  fbPlant[1].rPureDelay_s := 0.005;
    fbPlant[1].rGain         := 100.0;  fbPlant[1].rPosInit     := 100.0;
    fbPlant[2].rValveTC      := 0.014;  fbPlant[2].rPureDelay_s := 0.008;
    fbPlant[2].rGain         := 92.0;   fbPlant[2].rPosInit     := 100.0;
    fbPlant[3].rValveTC      := 0.008;  fbPlant[3].rPureDelay_s := 0.003;
    fbPlant[3].rGain         := 108.0;  fbPlant[3].rPosInit     := 100.0;
    FOR i := 1 TO 3 DO
        fbPlant[i].bReset := TRUE;
    END_FOR

    rPhaseRad     := 0.0;
    iCycleLog     := 0;
    iCycleCount   := 0;
    bNewCyclePrev := FALSE;
    FOR i := 0 TO 99 DO
        aRmsHistory[i]     := 0.0;
        aSyncErrHistory[i] := 0.0;
        aPeakErrHistory[i] := 0.0;
    END_FOR

    bInit     := TRUE;
    bResetSim := FALSE;
END_IF

// 清plant reset标志(只触发一次)
FOR i := 1 TO 3 DO
    IF fbPlant[i].bReset THEN fbPlant[i].bReset := FALSE; END_IF
END_FOR

// ============================================================
// 1. 生成正弦波目标(共3缸共享相同目标 → RIGID_SYNC)
// ============================================================
rPhaseRad := rPhaseRad + rTwoPi * rFreq * rTs;
bCycleEdge := FALSE;
IF rPhaseRad >= rTwoPi THEN
    rPhaseRad  := rPhaseRad - rTwoPi;
    bCycleEdge := TRUE;
END_IF
bNewCycle := bCycleEdge;

iPhaseIdx := REAL_TO_INT(rPhaseRad / rTwoPi * INT_TO_REAL(iPointsPerCycle));
IF iPhaseIdx >= iPointsPerCycle THEN iPhaseIdx := iPointsPerCycle - 1; END_IF
IF iPhaseIdx < 0                THEN iPhaseIdx := 0;                   END_IF

FOR i := 1 TO 3 DO
    aPosCmd[i] := rOffset + rAmp * SIN(rPhaseRad);
    aVelCmd[i] := rAmp * rTwoPi * rFreq * COS(rPhaseRad);
END_FOR

// ============================================================
// 2. ILC 修正
// ============================================================
fbILC(
    bEnable          := bEnableILC,
    bReset           := FALSE,
    iNumCylinders    := 3,
    iPointsPerCycle  := iPointsPerCycle,
    eCouplingMode    := E_ILC_CouplingMode.RIGID_SYNC,
    iPointIndex      := iPhaseIdx,
    bNewCycle        := bNewCycle,
    rPosCmd_arr      := aPosCmd,
    rVelCmd_arr      := aVelCmd,
    rPosFb_arr       := aPosFb,
    bChannelEnable   := aChEnable,
    rSyncRef_arr     := aSyncRef,
    rLearningGain    := 0.3,
    rSyncCoupling    := 0.6,
    rForgetting      := 0.99,
    rVelFFGain       := 0.0,
    rFF_Limit        := 10.0,
    rConvergeTol     := 0.1,
    rSafetyTol       := 30.0,
    nWarmupCycles    := 3,
    iPhaseLead       := 12,
    rQFilterStrength := 0.5,
    iUpdateChunkSize := 0,
    rPosCmdOut_arr   => aPosCmdOut
);

// 若ILC关闭,直接透传
IF NOT bEnableILC THEN
    FOR i := 1 TO 3 DO aPosCmdOut[i] := aPosCmd[i]; END_FOR
END_IF

// ============================================================
// 3. 每缸: PID → Valve → Plant
// ============================================================
FOR i := 1 TO 3 DO
    fbPID[i](
        rSetpoint := aPosCmdOut[i],
        rFeedback := aPosFb[i],
        rKp       := 0.04,
        rKi       := 1.0,
        rKd       := 0.0,
        rTs       := rTs,
        rOutMax   := 1.0,
        rOutMin   := -1.0,
        bEnable   := TRUE,
        rOutput   => aValveCmd[i]
    );
    fbPlant[i](
        rValveCmd := aValveCmd[i],
        rTs       := rTs,
        rPosOut   => aPosFb[i]
    );
END_FOR

// ============================================================
// 4. 周期边界记录(用于离线查看收敛曲线)
// ============================================================
IF bNewCycle AND NOT bNewCyclePrev THEN
    aRmsHistory[iCycleLog]     := fbILC.rGlobalRmsError;
    aSyncErrHistory[iCycleLog] := fbILC.rMaxSyncError;
    aPeakErrHistory[iCycleLog] := fbILC.rMaxTrackError;
    iCycleLog := iCycleLog + 1;
    IF iCycleLog >= 100 THEN iCycleLog := 0; END_IF
    iCycleCount := iCycleCount + 1;
END_IF
bNewCyclePrev := bNewCycle;

END_PROGRAM
