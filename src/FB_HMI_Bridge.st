// ============================================================
// File   : FB_HMI_Bridge.st
// 用途   : 把 ILC + 数据采集 + 参数辨识 + 故障状态聚合到分组STRUCT,
//          供 CODESYS Visu / WebVisu / TargetVisu 直接绑定
//
// ============================================================
// 推荐 Visu 布局(按页面/分区设计)
// ============================================================
//
// ┌─── Page 1: 总览 (Overview) ───────────────────────────────┐
// │  [状态指示灯] eState        : 文本+颜色 (IDLE/WARMUP/...)   │
// │  [周期计数器] iIteration    : 数值显示                       │
// │  [跟踪RMS表盘] rGlobalRmsErr : 0..10 mm                      │
// │  [同步误差表盘] rMaxSyncErr  : 0..5 mm                       │
// │  [模式选择] eCouplingMode   : 下拉框(独立/刚性/并联)         │
// │                                                              │
// │  按钮区:                                                     │
// │  [启动 ILC]   bCmdEnable                                     │
// │  [复位]       bCmdReset                                      │
// │  [紧急停机]   bCmdEStop                                      │
// │                                                              │
// │  报警区:                                                     │
// │  [报警栏]    aAlarms[0..7]  : 闪红+文字                      │
// └──────────────────────────────────────────────────────────┘
//
// ┌─── Page 2: 趋势 (Trends) ─────────────────────────────────┐
// │  [折线图]  aRmsTrend[0..63]   : 跟踪RMS随周期变化            │
// │  [折线图]  aSyncTrend[0..63]  : 同步误差随周期变化            │
// │  [折线图]  aPeakTrend[0..63]  : 峰值跟踪误差                  │
// │  [游标]   iTrendHead         : 最新点位置                     │
// └──────────────────────────────────────────────────────────┘
//
// ┌─── Page 3: 缸级明细 (Per-Cylinder Detail) ────────────────┐
// │  [表格]                                                      │
// │  Cyl# │ Enable │ RmsTrack │ RmsSync │ MaxFF │ OK              │
// │   1   │  ✓    │  0.12    │ 0.05    │ 0.8   │  ✓             │
// │   2   │  ✓    │  0.15    │ 0.07    │ 1.1   │  ✓             │
// │   ... 绑定到 aChannelStats[]                                 │
// └──────────────────────────────────────────────────────────┘
//
// ┌─── Page 4: 参数整定 (Tuning) ─────────────────────────────┐
// │  [按钮] bCmdStartPhaseTune : 启动相位整定                    │
// │  [显示] iPhaseLead_FromTuner                                 │
// │                                                              │
// │  [按钮] bCmdEstimateParams : 启动参数辨识                    │
// │  [显示] rL_Recommended, rLambda_Recommended, rAlpha_Recommended│
// │  [按钮] bCmdApplyParams    : 接受推荐值                      │
// │                                                              │
// │  [数值输入] 手动覆盖区:                                       │
// │   L  : rL_Manual                                             │
// │   λ  : rLambda_Manual                                        │
// │   α  : rAlpha_Manual                                         │
// │  [按钮] bCmdApplyManual                                      │
// │                                                              │
// │  [显示] stDiagL.sReason, stDiagLambda.sReason, ...           │
// └──────────────────────────────────────────────────────────┘
//
// ============================================================

TYPE ST_HMI_System :
STRUCT
    eState           : E_ILC_State;
    iIteration       : INT;
    iNumCylinders    : INT;
    iPointsPerCycle  : INT;
    eCouplingMode    : E_ILC_CouplingMode;
    bConverged       : BOOL;
    bFault           : BOOL;
END_STRUCT
END_TYPE

TYPE ST_HMI_Metrics :
STRUCT
    rGlobalRmsErr   : REAL;
    rMaxTrackErr    : REAL;
    rMaxSyncErr     : REAL;
    rWorstCyl_Track : INT;     // 编号:跟踪误差最大的缸
    rWorstCyl_Sync  : INT;     // 编号:同步误差最大的缸
END_STRUCT
END_TYPE

TYPE ST_HMI_Trend :
STRUCT
    aRmsTrend       : ARRAY[0..63] OF REAL;
    aSyncTrend      : ARRAY[0..63] OF REAL;
    aPeakTrend      : ARRAY[0..63] OF REAL;
    iTrendHead      : INT;
    iTrendCount     : INT;
END_STRUCT
END_TYPE

TYPE ST_HMI_Alarms :
STRUCT
    bAlmFault          : BOOL;     // ILC 故障
    bAlmSyncExceeded   : BOOL;     // 同步误差超限
    bAlmPhaseTuneFailed: BOOL;
    bAlmEstimatorFailed: BOOL;
    bAlmChannelDown    : BOOL;     // 任一通道 bChannelOK=FALSE
    sActiveAlarmText   : STRING(80);
END_STRUCT
END_TYPE

TYPE ST_HMI_Commands :
STRUCT
    // 主控
    bCmdEnable          : BOOL;
    bCmdReset           : BOOL;
    bCmdEStop           : BOOL;

    // 整定
    bCmdStartPhaseTune  : BOOL;
    bCmdAbortPhaseTune  : BOOL;
    bCmdEstimateParams  : BOOL;
    bCmdApplyParams     : BOOL;    // 接受辨识推荐
    bCmdApplyManual     : BOOL;    // 应用手动参数

    // 手动参数(操作员可调)
    rL_Manual           : REAL;
    rLambda_Manual      : REAL;
    rAlpha_Manual       : REAL;
    rFF_Limit_Manual    : REAL;
END_STRUCT
END_TYPE

TYPE ST_HMI_TuningResults :
STRUCT
    // 相位超前整定
    bPhaseTuneDone      : BOOL;
    iPhaseLead_FromTuner: INT;
    rEstDelay_s         : REAL;
    rEstTau_s           : REAL;

    // 参数辨识
    bParamEstimateDone  : BOOL;
    rL_Recommended      : REAL;
    rLambda_Recommended : REAL;
    rAlpha_Recommended  : REAL;
    rOverallConfidence  : REAL;
    sReasonL            : STRING(80);
    sReasonLambda       : STRING(80);
    sReasonAlpha        : STRING(80);
END_STRUCT
END_TYPE


FUNCTION_BLOCK FB_HMI_Bridge
VAR CONSTANT
    MAX_CYL : INT := 200;
    N_TREND : INT := 64;
END_VAR
VAR_INPUT
    bNewCycleEdge       : BOOL;

    // ---- ILC 状态 ----
    eState              : E_ILC_State;
    iIteration          : INT;
    iNumCylinders       : INT;
    iPointsPerCycle     : INT;
    eCouplingMode       : E_ILC_CouplingMode;
    bConverged          : BOOL;
    bFault              : BOOL;
    rGlobalRmsErr       : REAL;
    rMaxTrackErr        : REAL;
    rMaxSyncErr         : REAL;
    aChannelStats       : ARRAY[1..MAX_CYL] OF ST_ILC_ChannelStats;

    // ---- 整定/辨识结果 ----
    bPhaseTuneDone      : BOOL;
    bPhaseTuneFailed    : BOOL;
    iPhaseLead_FromTuner: INT;
    rEstDelay_s         : REAL;
    rEstTau_s           : REAL;
    bParamEstimateDone  : BOOL;
    bParamEstimateFailed: BOOL;
    rL_Recommended      : REAL;
    rLambda_Recommended : REAL;
    rAlpha_Recommended  : REAL;
    rOverallConfidence  : REAL;
    sReasonL            : STRING(80);
    sReasonLambda       : STRING(80);
    sReasonAlpha        : STRING(80);
END_VAR
VAR_OUTPUT
    stSystem            : ST_HMI_System;
    stMetrics           : ST_HMI_Metrics;
    stTrend             : ST_HMI_Trend;
    stAlarms            : ST_HMI_Alarms;
    stTuningResults     : ST_HMI_TuningResults;
END_VAR
VAR_IN_OUT
    stCmd               : ST_HMI_Commands;       // HMI写入,程序消费后清零
END_VAR
VAR
    bNewCyclePrev       : BOOL;
    i                   : INT;
    rMaxTrkLocal        : REAL;
    rMaxSyncLocal       : REAL;
    iWorstTrk           : INT;
    iWorstSync          : INT;
    bAnyChannelBad      : BOOL;
END_VAR

// ============================================================
// 1. 系统状态聚合
// ============================================================
stSystem.eState          := eState;
stSystem.iIteration      := iIteration;
stSystem.iNumCylinders   := iNumCylinders;
stSystem.iPointsPerCycle := iPointsPerCycle;
stSystem.eCouplingMode   := eCouplingMode;
stSystem.bConverged      := bConverged;
stSystem.bFault          := bFault;

// ============================================================
// 2. 实时指标
// ============================================================
stMetrics.rGlobalRmsErr := rGlobalRmsErr;
stMetrics.rMaxTrackErr  := rMaxTrackErr;
stMetrics.rMaxSyncErr   := rMaxSyncErr;

// 找最差的缸编号
rMaxTrkLocal   := 0.0;
rMaxSyncLocal  := 0.0;
iWorstTrk      := 0;
iWorstSync     := 0;
bAnyChannelBad := FALSE;
FOR i := 1 TO iNumCylinders DO
    IF aChannelStats[i].rPeakTrackError > rMaxTrkLocal THEN
        rMaxTrkLocal := aChannelStats[i].rPeakTrackError;
        iWorstTrk    := i;
    END_IF
    IF aChannelStats[i].rPeakSyncError > rMaxSyncLocal THEN
        rMaxSyncLocal := aChannelStats[i].rPeakSyncError;
        iWorstSync    := i;
    END_IF
    IF NOT aChannelStats[i].bChannelOK THEN bAnyChannelBad := TRUE; END_IF
END_FOR
stMetrics.rWorstCyl_Track := iWorstTrk;
stMetrics.rWorstCyl_Sync  := iWorstSync;

// ============================================================
// 3. 趋势更新(每个周期边界推一个新点到环形缓冲)
// ============================================================
IF bNewCycleEdge AND NOT bNewCyclePrev THEN
    stTrend.aRmsTrend [stTrend.iTrendHead] := rGlobalRmsErr;
    stTrend.aSyncTrend[stTrend.iTrendHead] := rMaxSyncErr;
    stTrend.aPeakTrend[stTrend.iTrendHead] := rMaxTrackErr;
    stTrend.iTrendHead := stTrend.iTrendHead + 1;
    IF stTrend.iTrendHead >= N_TREND THEN stTrend.iTrendHead := 0; END_IF
    IF stTrend.iTrendCount < N_TREND THEN
        stTrend.iTrendCount := stTrend.iTrendCount + 1;
    END_IF
END_IF
bNewCyclePrev := bNewCycleEdge;

// ============================================================
// 4. 报警生成
// ============================================================
stAlarms.bAlmFault           := bFault;
stAlarms.bAlmSyncExceeded    := (rMaxSyncErr > 1.0) AND NOT bConverged;
stAlarms.bAlmPhaseTuneFailed := bPhaseTuneFailed;
stAlarms.bAlmEstimatorFailed := bParamEstimateFailed;
stAlarms.bAlmChannelDown     := bAnyChannelBad;

// 最高优先级报警文本
IF bFault THEN
    stAlarms.sActiveAlarmText := 'ILC FAULT - sync error exceeded safety limit';
ELSIF bAnyChannelBad THEN
    stAlarms.sActiveAlarmText := 'One or more channels reporting unhealthy';
ELSIF bPhaseTuneFailed THEN
    stAlarms.sActiveAlarmText := 'Phase-lead tuning failed (step response timeout)';
ELSIF bParamEstimateFailed THEN
    stAlarms.sActiveAlarmText := 'Parameter estimation failed (insufficient data)';
ELSIF stAlarms.bAlmSyncExceeded THEN
    stAlarms.sActiveAlarmText := 'Sync error elevated';
ELSE
    stAlarms.sActiveAlarmText := '';
END_IF

// ============================================================
// 5. 整定/辨识结果传递
// ============================================================
stTuningResults.bPhaseTuneDone       := bPhaseTuneDone;
stTuningResults.iPhaseLead_FromTuner := iPhaseLead_FromTuner;
stTuningResults.rEstDelay_s          := rEstDelay_s;
stTuningResults.rEstTau_s            := rEstTau_s;

stTuningResults.bParamEstimateDone  := bParamEstimateDone;
stTuningResults.rL_Recommended      := rL_Recommended;
stTuningResults.rLambda_Recommended := rLambda_Recommended;
stTuningResults.rAlpha_Recommended  := rAlpha_Recommended;
stTuningResults.rOverallConfidence  := rOverallConfidence;
stTuningResults.sReasonL            := sReasonL;
stTuningResults.sReasonLambda       := sReasonLambda;
stTuningResults.sReasonAlpha        := sReasonAlpha;

// 命令通道:仅作为通道桥接,实际命令由调用方读取 stCmd.* 并消费
// (这里不清零,由调用方在响应命令后置位 FALSE)

END_FUNCTION_BLOCK
