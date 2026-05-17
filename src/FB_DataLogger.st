// ============================================================
// File   : FB_DataLogger.st
// 用途   : 多缸ILC的周期数据采集器,为离线参数辨识提供历史数据
//          - 在每个周期边界(bNewCycleEdge)采样关键指标
//          - 环形缓冲存储最近 N_HIST 个周期
//          - 同时输出衰减率/重复性等聚合指标,供 FB_OfflineParamEstimator 使用
//
// 内存占用: ST_CycleLog × N_HIST  ≈ 12 字节 × 64 = 768 字节
//          + 缸级日志 × MAX_CYL × N_HIST ≈ 12 × 200 × 64 ≈ 154 KB
// ============================================================

TYPE ST_CycleLog :
STRUCT
    iCycleNum     : INT;      // 全局周期编号
    rGlobalRms    : REAL;     // 全部缸跟踪RMS
    rMaxTrackErr  : REAL;     // 所有缸最大跟踪误差
    rMaxSyncErr   : REAL;     // 所有缸最大同步误差
END_STRUCT
END_TYPE

TYPE ST_ChannelCycleLog :
STRUCT
    rRmsTrack     : REAL;
    rRmsSync      : REAL;
    rMaxFF        : REAL;
END_STRUCT
END_TYPE


FUNCTION_BLOCK FB_DataLogger
VAR CONSTANT
    N_HIST  : INT := 64;      // 保存最近64个周期
    MAX_CYL : INT := 200;
END_VAR
VAR_INPUT
    bEnable           : BOOL;
    bReset            : BOOL;
    bNewCycleEdge     : BOOL;            // 上升沿:周期边界
    iNumCylinders     : INT;
    iCurrentIteration : INT;             // 来自 ILC iIteration
    rGlobalRms        : REAL;
    rMaxTrackErr      : REAL;
    rMaxSyncErr       : REAL;
    aChannelStats     : ARRAY[1..MAX_CYL] OF ST_ILC_ChannelStats;
END_VAR
VAR_OUTPUT
    iLoggedCycles      : INT;            // 已采集的周期数(达到N_HIST后保持)
    iHeadIdx           : INT;            // 环形缓冲最新数据的索引

    // 聚合指标(分析窗口取最近 iAnalyzeWindow 个周期)
    iAnalyzeWindow     : INT := 16;
    rRmsDecayRate      : REAL;           // RMS衰减率:0=不变,1=每周期减半
    rRmsSteadyMean     : REAL;           // 稳态RMS均值(分析窗口内)
    rRmsSteadyStdDev   : REAL;           // 稳态RMS标准差(衡量周期间重复性)
    rSyncToTrackRatio  : REAL;           // 同步误差/跟踪误差比值
    rRepeatability     : REAL;           // 0~1,越高越重复
    bSufficientData    : BOOL;           // 数据足够进行辨识
END_VAR
VAR
    aCycleLog          : ARRAY[0..63] OF ST_CycleLog;
    aChannelLog        : ARRAY[0..63, 1..200] OF ST_ChannelCycleLog;
    iHead              : INT;            // 下一次写入位置
    bNewCyclePrev      : BOOL;
    i, k, iIdx         : INT;
    rSum               : REAL;
    rSum2              : REAL;
    rMean              : REAL;
    rVar               : REAL;
    iCount             : INT;
    rLogRatio          : REAL;
    rLastRms           : REAL;
    rFirstRms          : REAL;
    rSumSync           : REAL;
    rSumTrack          : REAL;
    iAnaCycles         : INT;
END_VAR

// ============================================================
// 复位
// ============================================================
IF bReset OR NOT bEnable THEN
    IF bReset THEN
        FOR i := 0 TO N_HIST - 1 DO
            aCycleLog[i].iCycleNum    := 0;
            aCycleLog[i].rGlobalRms   := 0.0;
            aCycleLog[i].rMaxTrackErr := 0.0;
            aCycleLog[i].rMaxSyncErr  := 0.0;
            FOR k := 1 TO MAX_CYL DO
                aChannelLog[i, k].rRmsTrack := 0.0;
                aChannelLog[i, k].rRmsSync  := 0.0;
                aChannelLog[i, k].rMaxFF    := 0.0;
            END_FOR
        END_FOR
        iHead             := 0;
        iLoggedCycles     := 0;
        iHeadIdx          := 0;
        bNewCyclePrev     := FALSE;
        rRmsDecayRate     := 0.0;
        rRmsSteadyMean    := 0.0;
        rRmsSteadyStdDev  := 0.0;
        rSyncToTrackRatio := 0.0;
        rRepeatability    := 0.0;
        bSufficientData   := FALSE;
    END_IF
    IF NOT bEnable THEN RETURN; END_IF
END_IF

// ============================================================
// 周期边界采样
// ============================================================
IF bNewCycleEdge AND NOT bNewCyclePrev THEN
    aCycleLog[iHead].iCycleNum    := iCurrentIteration;
    aCycleLog[iHead].rGlobalRms   := rGlobalRms;
    aCycleLog[iHead].rMaxTrackErr := rMaxTrackErr;
    aCycleLog[iHead].rMaxSyncErr  := rMaxSyncErr;

    FOR k := 1 TO iNumCylinders DO
        aChannelLog[iHead, k].rRmsTrack := aChannelStats[k].rRmsTrackError;
        aChannelLog[iHead, k].rRmsSync  := aChannelStats[k].rRmsSyncError;
        aChannelLog[iHead, k].rMaxFF    := aChannelStats[k].rMaxFF;
    END_FOR

    iHeadIdx := iHead;
    iHead := iHead + 1;
    IF iHead >= N_HIST THEN iHead := 0; END_IF
    IF iLoggedCycles < N_HIST THEN
        iLoggedCycles := iLoggedCycles + 1;
    END_IF

    // ---- 计算聚合指标 ----
    iAnaCycles := iAnalyzeWindow;
    IF iAnaCycles > iLoggedCycles THEN iAnaCycles := iLoggedCycles; END_IF
    bSufficientData := (iLoggedCycles >= 8);

    IF iAnaCycles >= 2 THEN
        // 1. RMS衰减率: ρ = (rms_last / rms_first)^(1/(N-1))
        //    然后 decayRate = 1 - ρ (每周期RMS减小的比例)
        // 取分析窗口的第一个和最后一个周期
        iIdx := iHeadIdx - (iAnaCycles - 1);
        WHILE iIdx < 0 DO iIdx := iIdx + N_HIST; END_WHILE
        rFirstRms := aCycleLog[iIdx].rGlobalRms;
        rLastRms  := aCycleLog[iHeadIdx].rGlobalRms;

        IF rFirstRms > 1.0E-6 AND rLastRms > 1.0E-9 THEN
            rLogRatio := LN(rLastRms / rFirstRms) / INT_TO_REAL(iAnaCycles - 1);
            rRmsDecayRate := 1.0 - EXP(rLogRatio);
        ELSE
            rRmsDecayRate := 0.0;
        END_IF

        // 2. 稳态均值 & 标准差(取分析窗口后半段)
        rSum  := 0.0;
        rSum2 := 0.0;
        iCount := 0;
        FOR i := iAnaCycles / 2 TO iAnaCycles - 1 DO
            iIdx := iHeadIdx - i;
            WHILE iIdx < 0 DO iIdx := iIdx + N_HIST; END_WHILE
            rSum  := rSum  + aCycleLog[iIdx].rGlobalRms;
            rSum2 := rSum2 + aCycleLog[iIdx].rGlobalRms * aCycleLog[iIdx].rGlobalRms;
            iCount := iCount + 1;
        END_FOR
        IF iCount > 0 THEN
            rMean := rSum / INT_TO_REAL(iCount);
            rVar  := rSum2 / INT_TO_REAL(iCount) - rMean * rMean;
            IF rVar < 0.0 THEN rVar := 0.0; END_IF
            rRmsSteadyMean   := rMean;
            rRmsSteadyStdDev := SQRT(rVar);
        END_IF

        // 3. 同步/跟踪误差比值(分析窗口平均)
        rSumSync  := 0.0;
        rSumTrack := 0.0;
        FOR i := 0 TO iAnaCycles - 1 DO
            iIdx := iHeadIdx - i;
            WHILE iIdx < 0 DO iIdx := iIdx + N_HIST; END_WHILE
            rSumSync  := rSumSync  + aCycleLog[iIdx].rMaxSyncErr;
            rSumTrack := rSumTrack + aCycleLog[iIdx].rMaxTrackErr;
        END_FOR
        IF rSumTrack > 1.0E-6 THEN
            rSyncToTrackRatio := rSumSync / rSumTrack;
        ELSE
            rSyncToTrackRatio := 0.0;
        END_IF

        // 4. 重复性指标:RMS标准差 vs RMS均值,越小越重复
        //    repeatability = 1 - min(stddev/mean, 1)
        IF rRmsSteadyMean > 1.0E-6 THEN
            rRepeatability := 1.0 - rRmsSteadyStdDev / rRmsSteadyMean;
            IF rRepeatability < 0.0 THEN rRepeatability := 0.0; END_IF
            IF rRepeatability > 1.0 THEN rRepeatability := 1.0; END_IF
        ELSE
            rRepeatability := 1.0;
        END_IF
    END_IF
END_IF
bNewCyclePrev := bNewCycleEdge;

END_FUNCTION_BLOCK
