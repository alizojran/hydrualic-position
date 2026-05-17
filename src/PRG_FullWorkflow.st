// ============================================================
// File   : PRG_FullWorkflow.st
// 用途   : 端到端工作流示例:
//          1. 相位超前自整定 (FB_PhaseLeadTuner)
//          2. ILC 正常运行 + 数据采集 (FB_CrossCoupledILC + FB_DataLogger)
//          3. 离线参数辨识 (FB_OfflineParamEstimator)
//          4. 操作员确认应用,重置ILC重学习
//          5. HMI 桥接 (FB_HMI_Bridge)
//
// 设计:
//   - FB_CrossCoupledILC 每周期调用一次(在程序末尾)
//   - 工作流状态机只修改使能标志和参数,不直接调ILC
//   - FB_DataLogger / FB_HMI_Bridge 始终运行
//
// 把本程序挂到 1ms 周期任务(MainTask)。HMI 任务可独立 500ms 周期读取
// stHMI_* 变量。
// ============================================================

PROGRAM PRG_FullWorkflow
VAR
    // ---- 核心FB ----
    fbILC               : FB_CrossCoupledILC;
    fbTuner             : FB_PhaseLeadTuner;
    fbLogger            : FB_DataLogger;
    fbEstimator         : FB_OfflineParamEstimator;
    fbHMI               : FB_HMI_Bridge;

    // ---- I/O 数组 ----
    aPosCmd             : ARRAY[1..200] OF REAL;
    aVelCmd             : ARRAY[1..200] OF REAL;
    aPosFb              : ARRAY[1..200] OF REAL;
    aSyncRef            : ARRAY[1..200] OF REAL;
    aChEnable           : ARRAY[1..200] OF BOOL;
    aPosCmdOut          : ARRAY[1..200] OF REAL;

    // ---- HMI 桥接(可绑Visu)----
    stHMI_System        : ST_HMI_System;
    stHMI_Metrics       : ST_HMI_Metrics;
    stHMI_Trend         : ST_HMI_Trend;
    stHMI_Alarms        : ST_HMI_Alarms;
    stHMI_Tuning        : ST_HMI_TuningResults;
    stHMI_Cmd           : ST_HMI_Commands;          // HMI写入

    // ---- 工作流状态 ----
    eWorkflow           : INT := 0;
    //   0 = IDLE
    //   1 = PHASE_TUNING
    //   2 = ILC_RUN
    //   3 = PARAM_ESTIMATING
    //   4 = WAITING_PARAM_APPROVAL
    //   5 = APPLIED_RESTART (单周期脉冲)

    // ---- ILC 调用参数(状态机修改这些)----
    bILC_Enable         : BOOL := FALSE;
    bILC_Reset_Pulse    : BOOL := FALSE;
    bTuner_Start        : BOOL := FALSE;
    bTuner_Abort        : BOOL := FALSE;
    bEstimator_Execute  : BOOL := FALSE;

    rL_Active           : REAL := 0.3;
    rLambda_Active      : REAL := 0.5;
    rAlpha_Active       : REAL := 0.98;
    iPhaseLead_Active   : INT  := 10;
    rFFLimit_Active     : REAL := 5.0;

    // ---- 整定中所选缸 ----
    iTuningCylinder     : INT := 1;

    // ---- 周期时钟(由SoftMotion主任务提供,这里占位)----
    iPhaseIdx           : INT;
    bNewCycle           : BOOL;
    bNewCycleEdge       : BOOL;
    bNewCyclePrev_WF    : BOOL;
    iPointsPerCycle     : INT := 1000;

    i                   : INT;
    bInit               : BOOL := FALSE;
END_VAR

// ============================================================
// 初始化(只跑一次)
// ============================================================
IF NOT bInit THEN
    FOR i := 1 TO 200 DO aChEnable[i] := FALSE; END_FOR
    aChEnable[1] := TRUE; aChEnable[2] := TRUE; aChEnable[3] := TRUE;
    bInit := TRUE;
END_IF

bNewCycleEdge    := bNewCycle AND NOT bNewCyclePrev_WF;
bNewCyclePrev_WF := bNewCycle;

// 默认参数:每周期开始时清零脉冲
bILC_Reset_Pulse := FALSE;

// ============================================================
// 工作流状态机:只修改标志位,不直接调FB
// ============================================================
CASE eWorkflow OF

0:  // IDLE
    bILC_Enable        := FALSE;
    bTuner_Start       := FALSE;
    bEstimator_Execute := FALSE;
    IF stHMI_Cmd.bCmdStartPhaseTune THEN
        eWorkflow := 1;
        bTuner_Start := TRUE;
        stHMI_Cmd.bCmdStartPhaseTune := FALSE;
    ELSIF stHMI_Cmd.bCmdEnable THEN
        eWorkflow := 2;
        bILC_Enable := TRUE;
        stHMI_Cmd.bCmdEnable := FALSE;
    END_IF

1:  // PHASE_TUNING
    bILC_Enable  := FALSE;
    bTuner_Start := TRUE;
    bTuner_Abort := stHMI_Cmd.bCmdAbortPhaseTune;
    IF fbTuner.bDone THEN
        iPhaseLead_Active := fbTuner.iEstLeadPts;
        bTuner_Start      := FALSE;
        eWorkflow         := 0;
    ELSIF fbTuner.bFailed OR stHMI_Cmd.bCmdAbortPhaseTune THEN
        bTuner_Start      := FALSE;
        bTuner_Abort      := FALSE;
        stHMI_Cmd.bCmdAbortPhaseTune := FALSE;
        eWorkflow         := 0;
    END_IF

2:  // ILC_RUN
    bILC_Enable := TRUE;
    IF stHMI_Cmd.bCmdEStop THEN
        bILC_Enable := FALSE;
        eWorkflow   := 0;
        stHMI_Cmd.bCmdEStop := FALSE;
    ELSIF stHMI_Cmd.bCmdReset THEN
        bILC_Reset_Pulse := TRUE;
        stHMI_Cmd.bCmdReset := FALSE;
    ELSIF stHMI_Cmd.bCmdEstimateParams THEN
        eWorkflow := 3;
        bEstimator_Execute := TRUE;
        stHMI_Cmd.bCmdEstimateParams := FALSE;
    ELSIF stHMI_Cmd.bCmdApplyManual THEN
        rL_Active       := stHMI_Cmd.rL_Manual;
        rLambda_Active  := stHMI_Cmd.rLambda_Manual;
        rAlpha_Active   := stHMI_Cmd.rAlpha_Manual;
        rFFLimit_Active := stHMI_Cmd.rFF_Limit_Manual;
        bILC_Reset_Pulse := TRUE;   // 应用新参数后重置学习
        stHMI_Cmd.bCmdApplyManual := FALSE;
    END_IF

3:  // PARAM_ESTIMATING - ILC继续运行,辨识器独立工作
    bILC_Enable        := TRUE;
    bEstimator_Execute := TRUE;
    IF fbEstimator.bDone OR fbEstimator.bFailed THEN
        bEstimator_Execute := FALSE;
        eWorkflow := 4;
    END_IF

4:  // WAITING_PARAM_APPROVAL
    bILC_Enable := TRUE;
    IF stHMI_Cmd.bCmdApplyParams AND fbEstimator.bDone THEN
        rL_Active      := fbEstimator.rL_Recommended;
        rLambda_Active := fbEstimator.rLambda_Recommended;
        rAlpha_Active  := fbEstimator.rAlpha_Recommended;
        stHMI_Cmd.bCmdApplyParams := FALSE;
        eWorkflow      := 5;
    ELSIF stHMI_Cmd.bCmdReset THEN
        eWorkflow := 2;
        stHMI_Cmd.bCmdReset := FALSE;
    END_IF

5:  // APPLIED_RESTART - 应用新参数后重置ILC学习(单周期脉冲)
    bILC_Enable      := TRUE;
    bILC_Reset_Pulse := TRUE;
    eWorkflow        := 2;

END_CASE

// ============================================================
// 相位整定器(总是调用,内部通过bStart上升沿触发)
// ============================================================
fbTuner(
    bStart       := bTuner_Start,
    bAbort       := bTuner_Abort,
    rTs          := 0.001,
    rPosFb       := aPosFb[iTuningCylinder],
    rStepSize    := 5.0,
    rSettleTol   := 0.05,
    iSettlePts   := 200,
    iMaxMeasPts  := 3000
);
// 整定期间把tuner输出的指令送到所选缸
IF fbTuner.bRunning THEN
    aPosCmd[iTuningCylinder] := fbTuner.rStepCmdOut;
END_IF

// ============================================================
// ILC 主调用(每周期一次)
// ============================================================
fbILC(
    bEnable          := bILC_Enable,
    bReset           := bILC_Reset_Pulse,
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
    rLearningGain    := rL_Active,
    rSyncCoupling    := rLambda_Active,
    rForgetting      := rAlpha_Active,
    rFF_Limit        := rFFLimit_Active,
    rConvergeTol     := 0.05,
    rSafetyTol       := 1.0,
    nWarmupCycles    := 3,
    iPhaseLead       := iPhaseLead_Active,
    rQFilterStrength := 0.5,
    iUpdateChunkSize := 0,
    rPosCmdOut_arr   => aPosCmdOut
);

// ============================================================
// 数据采集
// ============================================================
fbLogger(
    bEnable           := bILC_Enable,
    bReset            := bILC_Reset_Pulse,
    bNewCycleEdge     := bNewCycleEdge,
    iNumCylinders     := 3,
    iCurrentIteration := fbILC.iIteration,
    rGlobalRms        := fbILC.rGlobalRmsError,
    rMaxTrackErr      := fbILC.rMaxTrackError,
    rMaxSyncErr       := fbILC.rMaxSyncError,
    aChannelStats     := fbILC.aChannelStats
);

// ============================================================
// 离线参数辨识(由 bEstimator_Execute 上升沿触发)
// ============================================================
fbEstimator(
    bExecute            := bEstimator_Execute,
    bDataSufficient     := fbLogger.bSufficientData,
    iLoggedCycles       := fbLogger.iLoggedCycles,
    rRmsDecayRate       := fbLogger.rRmsDecayRate,
    rRmsSteadyMean      := fbLogger.rRmsSteadyMean,
    rRmsSteadyStdDev    := fbLogger.rRmsSteadyStdDev,
    rSyncToTrackRatio   := fbLogger.rSyncToTrackRatio,
    rRepeatability      := fbLogger.rRepeatability,
    rL_Current          := rL_Active,
    rLambda_Current     := rLambda_Active,
    rAlpha_Current      := rAlpha_Active,
    rTargetDecayRate    := 0.25
);

// ============================================================
// HMI 桥接
// ============================================================
fbHMI(
    bNewCycleEdge        := bNewCycleEdge,
    eState               := fbILC.eState,
    iIteration           := fbILC.iIteration,
    iNumCylinders        := 3,
    iPointsPerCycle      := iPointsPerCycle,
    eCouplingMode        := E_ILC_CouplingMode.RIGID_SYNC,
    bConverged           := fbILC.bConverged,
    bFault               := fbILC.bFault,
    rGlobalRmsErr        := fbILC.rGlobalRmsError,
    rMaxTrackErr         := fbILC.rMaxTrackError,
    rMaxSyncErr          := fbILC.rMaxSyncError,
    aChannelStats        := fbILC.aChannelStats,
    bPhaseTuneDone       := fbTuner.bDone,
    bPhaseTuneFailed     := fbTuner.bFailed,
    iPhaseLead_FromTuner := fbTuner.iEstLeadPts,
    rEstDelay_s          := fbTuner.rEstDelay_s,
    rEstTau_s            := fbTuner.rEstTau_s,
    bParamEstimateDone   := fbEstimator.bDone,
    bParamEstimateFailed := fbEstimator.bFailed,
    rL_Recommended       := fbEstimator.rL_Recommended,
    rLambda_Recommended  := fbEstimator.rLambda_Recommended,
    rAlpha_Recommended   := fbEstimator.rAlpha_Recommended,
    rOverallConfidence   := fbEstimator.rOverallConfidence,
    sReasonL             := fbEstimator.stDiagL.sReason,
    sReasonLambda        := fbEstimator.stDiagLambda.sReason,
    sReasonAlpha         := fbEstimator.stDiagAlpha.sReason,
    stCmd                := stHMI_Cmd,
    stSystem             => stHMI_System,
    stMetrics            => stHMI_Metrics,
    stTrend              => stHMI_Trend,
    stAlarms             => stHMI_Alarms,
    stTuningResults      => stHMI_Tuning
);

END_PROGRAM
