// ============================================================
// File   : FB_CrossCoupledILC.st
// 功能   : 多油缸交叉耦合迭代学习控制(Cross-Coupled ILC)
//          - 跟踪误差学习: u_{k+1} = α·u_k + L·(e_track - λ·e_sync)
//          - 周期内零相移Q滤波,防共振发散
//          - 相位超前补偿系统延迟
//          - 三种耦合模式(独立/刚性同步/并联机构)
//          - 周期末前馈表更新分块分摊,不阻塞RT主任务
// 平台   : 自研CODESYS / 4核ARM 1.8GHz / RT-Linux
// 容量   : 最多 200 缸,4000 采样点/周期
//
// 调用频率: 由SoftMotion主时钟驱动,每个采样点调用一次
// ============================================================

FUNCTION_BLOCK FB_CrossCoupledILC
VAR CONSTANT
    MAX_CYL       : INT  := 200;
    MAX_PTS       : INT  := 4000;
    MIN_DENOM     : REAL := 1.0E-6;
    CONVERGE_HOLD : INT  := 3;    // 连续N周期低于容差才判定收敛
END_VAR

VAR_INPUT
    bEnable          : BOOL;
    bReset           : BOOL;

    // ---- 系统配置 ----
    iNumCylinders    : INT;                       // 实际缸数 1..MAX_CYL
    iPointsPerCycle  : INT;                       // 每周期采样点数 10..MAX_PTS
    eCouplingMode    : E_ILC_CouplingMode;

    // ---- 周期时钟(由SoftMotion主任务广播)----
    iPointIndex      : INT;                       // 0..iPointsPerCycle-1
    bNewCycle        : BOOL;                      // 上升沿:新周期开始

    // ---- 每缸实时输入(SoftMotion输出 + 反馈)----
    rPosCmd_arr      : ARRAY[1..MAX_CYL] OF REAL; // 位置指令 (mm)
    rVelCmd_arr      : ARRAY[1..MAX_CYL] OF REAL; // 速度指令 (mm/s)
    rPosFb_arr       : ARRAY[1..MAX_CYL] OF REAL; // 位置反馈 (mm)
    bChannelEnable   : ARRAY[1..MAX_CYL] OF BOOL; // 每缸独立使能
    rSyncRef_arr     : ARRAY[1..MAX_CYL] OF REAL; // 并联机构模式同步参考(用户提供)

    // ---- 学习参数(可在线调整)----
    rLearningGain    : REAL := 0.3;   // L : 学习增益
    rSyncCoupling    : REAL := 0.5;   // λ : 同步耦合权重
    rForgetting      : REAL := 0.98;  // α : 遗忘因子,<1.0对抗非重复扰动
    rVelFFGain       : REAL := 0.0;   // 速度前馈增益(可选)

    // ---- 精度/安全 ----
    rFF_Limit        : REAL := 5.0;   // 前馈幅值限幅(mm)
    rConvergeTol     : REAL := 0.05;  // 跟踪RMS<此值视为收敛
    rSafetyTol       : REAL := 2.0;   // 同步误差超此值触发故障
    nWarmupCycles    : INT  := 3;

    // ---- 相位与滤波 ----
    iPhaseLead       : INT  := 0;     // 相位超前点数(补偿系统时滞)
    rQFilterStrength : REAL := 0.5;   // 0=不滤波, 1=最强(三点平均)

    // ---- 实时性控制 ----
    iUpdateChunkSize : INT  := 0;     // 0=单周期一次更新完;>0=每个采样点更新K个缸
END_VAR

VAR_OUTPUT
    eState           : E_ILC_State;
    iIteration       : INT;
    bConverged       : BOOL;
    bFault           : BOOL;
    rMaxTrackError   : REAL;
    rMaxSyncError    : REAL;
    rGlobalRmsError  : REAL;

    rILC_FF_arr      : ARRAY[1..MAX_CYL] OF REAL; // 当前点ILC前馈(已含速度FF)
    rPosCmdOut_arr   : ARRAY[1..MAX_CYL] OF REAL; // = rPosCmd + rILC_FF (送到位置环)
    aChannelStats    : ARRAY[1..MAX_CYL] OF ST_ILC_ChannelStats;
END_VAR

VAR
    // ---- ILC前馈表(每缸一行 × 每周期采样点)----
    rFF_Table        : ARRAY[1..MAX_CYL, 0..MAX_PTS-1] OF REAL;
    // ---- 本周期误差缓存(周期末用于更新FF表)----
    rErrCapture      : ARRAY[1..MAX_CYL, 0..MAX_PTS-1] OF REAL;

    // ---- 周期/状态 ----
    iIterCount       : INT;
    bNewCyclePrev    : BOOL;
    nConsecConverge  : INT;

    // ---- 周期内统计累计 ----
    rTrackErrSum2    : ARRAY[1..MAX_CYL] OF REAL;
    rSyncErrSum2     : ARRAY[1..MAX_CYL] OF REAL;
    rPeakTrkAbs      : ARRAY[1..MAX_CYL] OF REAL;
    rPeakSyncAbs     : ARRAY[1..MAX_CYL] OF REAL;
    iSampleCount     : INT;

    // ---- 分块更新状态 ----
    bUpdatePending   : BOOL;
    iUpdateCylNext   : INT;

    // ---- 工作变量 ----
    i, j             : INT;
    iEndCyl          : INT;
    rMean            : REAL;
    rTrackErr        : REAL;
    rSyncErr         : REAL;
    rCombinedErr     : REAL;
    rSum             : REAL;
    rGlobalSum2      : REAL;
    iActiveCount     : INT;
    iLeadIdx         : INT;
    iPrevIdx         : INT;
    iNextIdx         : INT;
    iLeadWrap        : INT;
    rFiltered        : REAL;
    rNewFF           : REAL;
    rMaxFFLocal      : REAL;
    rAbsTrk          : REAL;
    rAbsSync         : REAL;
END_VAR

// ============================================================
// 1. 复位 / 禁用
// ============================================================
IF bReset OR NOT bEnable THEN
    IF bReset THEN
        FOR i := 1 TO MAX_CYL DO
            FOR j := 0 TO MAX_PTS - 1 DO
                rFF_Table[i, j]   := 0.0;
                rErrCapture[i, j] := 0.0;
            END_FOR
            rTrackErrSum2[i] := 0.0;
            rSyncErrSum2[i]  := 0.0;
            rPeakTrkAbs[i]   := 0.0;
            rPeakSyncAbs[i]  := 0.0;
            aChannelStats[i].rRmsTrackError  := 0.0;
            aChannelStats[i].rPeakTrackError := 0.0;
            aChannelStats[i].rRmsSyncError   := 0.0;
            aChannelStats[i].rPeakSyncError  := 0.0;
            aChannelStats[i].rMaxFF          := 0.0;
            aChannelStats[i].bChannelOK      := TRUE;
        END_FOR
        iIterCount       := 0;
        iIteration       := 0;
        nConsecConverge  := 0;
        bConverged       := FALSE;
        bFault           := FALSE;
        bUpdatePending   := FALSE;
        iUpdateCylNext   := 1;
        eState           := E_ILC_State.IDLE;
        rMaxTrackError   := 0.0;
        rMaxSyncError    := 0.0;
        rGlobalRmsError  := 0.0;
    END_IF
    iSampleCount := 0;
    FOR i := 1 TO MAX_CYL DO
        rILC_FF_arr[i]    := 0.0;
        rPosCmdOut_arr[i] := rPosCmd_arr[i];
    END_FOR
    IF NOT bEnable THEN
        eState := E_ILC_State.IDLE;
        RETURN;
    END_IF
END_IF

// ============================================================
// 2. 输入校验
// ============================================================
IF iNumCylinders < 1 OR iNumCylinders > MAX_CYL THEN
    bFault := TRUE; eState := E_ILC_State.FAULT; RETURN;
END_IF
IF iPointsPerCycle < 10 OR iPointsPerCycle > MAX_PTS THEN
    bFault := TRUE; eState := E_ILC_State.FAULT; RETURN;
END_IF
IF iPointIndex < 0 THEN iPointIndex := 0; END_IF
IF iPointIndex >= iPointsPerCycle THEN iPointIndex := iPointsPerCycle - 1; END_IF

// ============================================================
// 3. 故障状态:输出冻结为透传
// ============================================================
IF bFault THEN
    FOR i := 1 TO iNumCylinders DO
        rILC_FF_arr[i]    := 0.0;
        rPosCmdOut_arr[i] := rPosCmd_arr[i];
    END_FOR
    eState := E_ILC_State.FAULT;
    RETURN;
END_IF

// ============================================================
// 4. 状态机标识
// ============================================================
IF iIterCount < nWarmupCycles THEN
    eState := E_ILC_State.WARMUP;
ELSIF bConverged THEN
    eState := E_ILC_State.CONVERGED;
ELSE
    eState := E_ILC_State.LEARNING;
END_IF

// ============================================================
// 5. 周期边界:统计 + 收敛/故障判断 + 触发FF表更新
// ============================================================
IF bNewCycle AND NOT bNewCyclePrev THEN

    // ---- 5.1 计算上周期统计 ----
    rGlobalSum2    := 0.0;
    iActiveCount   := 0;
    rMaxTrackError := 0.0;
    rMaxSyncError  := 0.0;

    IF iSampleCount > 0 THEN
        FOR i := 1 TO iNumCylinders DO
            IF bChannelEnable[i] THEN
                aChannelStats[i].rRmsTrackError  := SQRT(rTrackErrSum2[i] / INT_TO_REAL(iSampleCount));
                aChannelStats[i].rRmsSyncError   := SQRT(rSyncErrSum2[i]  / INT_TO_REAL(iSampleCount));
                aChannelStats[i].rPeakTrackError := rPeakTrkAbs[i];
                aChannelStats[i].rPeakSyncError  := rPeakSyncAbs[i];
                aChannelStats[i].bChannelOK      := rPeakSyncAbs[i] < rSafetyTol;

                rGlobalSum2  := rGlobalSum2 + rTrackErrSum2[i];
                iActiveCount := iActiveCount + 1;

                IF rPeakTrkAbs[i] > rMaxTrackError THEN
                    rMaxTrackError := rPeakTrkAbs[i];
                END_IF
                IF rPeakSyncAbs[i] > rMaxSyncError THEN
                    rMaxSyncError := rPeakSyncAbs[i];
                END_IF
            END_IF
        END_FOR

        IF iActiveCount > 0 THEN
            rGlobalRmsError := SQRT(rGlobalSum2 /
                (INT_TO_REAL(iActiveCount) * INT_TO_REAL(iSampleCount)));
        END_IF
    END_IF

    // ---- 5.2 安全检查:同步误差越限 → 故障 ----
    IF rMaxSyncError > rSafetyTol AND iIterCount >= nWarmupCycles THEN
        bFault := TRUE;
        eState := E_ILC_State.FAULT;
    END_IF

    // ---- 5.3 收敛判断:连续N周期RMS < 容差 ----
    IF rGlobalRmsError < rConvergeTol AND iIterCount >= nWarmupCycles THEN
        nConsecConverge := nConsecConverge + 1;
        IF nConsecConverge >= CONVERGE_HOLD THEN
            bConverged := TRUE;
        END_IF
    ELSE
        nConsecConverge := 0;
        bConverged      := FALSE;
    END_IF

    // ---- 5.4 触发FF表更新(暖机后,非故障,非已收敛)----
    IF iIterCount >= nWarmupCycles AND NOT bFault AND NOT bConverged THEN
        bUpdatePending := TRUE;
        iUpdateCylNext := 1;
    END_IF

    // ---- 5.5 复位本周期累计 ----
    FOR i := 1 TO MAX_CYL DO
        rTrackErrSum2[i] := 0.0;
        rSyncErrSum2[i]  := 0.0;
        rPeakTrkAbs[i]   := 0.0;
        rPeakSyncAbs[i]  := 0.0;
    END_FOR
    iSampleCount := 0;

    iIterCount := iIterCount + 1;
    iIteration := iIterCount;
END_IF
bNewCyclePrev := bNewCycle;

// ============================================================
// 6. FF表更新(分块,避免单次循环阻塞RT任务)
// ============================================================
// iUpdateChunkSize = 0 → 整次更新在此处完成
// iUpdateChunkSize > 0 → 每次循环只更新K个缸,分摊到多个采样点
IF bUpdatePending THEN
    IF iUpdateChunkSize <= 0 THEN
        iEndCyl := iNumCylinders;
    ELSE
        iEndCyl := iUpdateCylNext + iUpdateChunkSize - 1;
        IF iEndCyl > iNumCylinders THEN iEndCyl := iNumCylinders; END_IF
    END_IF

    // 预归一化相位超前,避免内层循环重复wrap
    iLeadWrap := iPhaseLead MOD iPointsPerCycle;
    IF iLeadWrap < 0 THEN iLeadWrap := iLeadWrap + iPointsPerCycle; END_IF

    FOR i := iUpdateCylNext TO iEndCyl DO
        IF bChannelEnable[i] THEN
            rMaxFFLocal := 0.0;
            FOR j := 0 TO iPointsPerCycle - 1 DO
                // 相位超前(单次加+条件减,O(1))
                iLeadIdx := j + iLeadWrap;
                IF iLeadIdx >= iPointsPerCycle THEN
                    iLeadIdx := iLeadIdx - iPointsPerCycle;
                END_IF

                // Q滤波:对前馈表做零相移三点平均
                IF rQFilterStrength > 0.001 THEN
                    iPrevIdx := j - 1;
                    IF iPrevIdx < 0 THEN iPrevIdx := iPointsPerCycle - 1; END_IF
                    iNextIdx := j + 1;
                    IF iNextIdx >= iPointsPerCycle THEN iNextIdx := 0; END_IF

                    rFiltered := (rFF_Table[i, iPrevIdx]
                                + rFF_Table[i, j] * 2.0
                                + rFF_Table[i, iNextIdx]) * 0.25;
                    rFiltered := rFF_Table[i, j] * (1.0 - rQFilterStrength)
                               + rFiltered      * rQFilterStrength;
                ELSE
                    rFiltered := rFF_Table[i, j];
                END_IF

                // 学习律 + 遗忘因子
                rNewFF := rForgetting   * rFiltered
                        + rLearningGain * rErrCapture[i, iLeadIdx];

                // 限幅
                IF rNewFF >  rFF_Limit THEN rNewFF :=  rFF_Limit; END_IF
                IF rNewFF < -rFF_Limit THEN rNewFF := -rFF_Limit; END_IF

                rFF_Table[i, j] := rNewFF;

                IF ABS(rNewFF) > rMaxFFLocal THEN rMaxFFLocal := ABS(rNewFF); END_IF
            END_FOR
            aChannelStats[i].rMaxFF := rMaxFFLocal;
        END_IF
    END_FOR

    iUpdateCylNext := iEndCyl + 1;
    IF iUpdateCylNext > iNumCylinders THEN
        bUpdatePending := FALSE;
    END_IF
END_IF

// ============================================================
// 7. 每采样点:计算同步参考,生成误差,产生输出
// ============================================================

// ---- 7.1 同步参考(仅RIGID_SYNC模式需要平均反馈)----
IF eCouplingMode = E_ILC_CouplingMode.RIGID_SYNC THEN
    rSum         := 0.0;
    iActiveCount := 0;
    FOR i := 1 TO iNumCylinders DO
        IF bChannelEnable[i] THEN
            rSum         := rSum + rPosFb_arr[i];
            iActiveCount := iActiveCount + 1;
        END_IF
    END_FOR
    IF iActiveCount > 0 THEN
        rMean := rSum / INT_TO_REAL(iActiveCount);
    ELSE
        rMean := 0.0;
    END_IF
END_IF

// ---- 7.2 逐缸:误差计算 + 输出生成 ----
FOR i := 1 TO iNumCylinders DO
    IF NOT bChannelEnable[i] THEN
        rILC_FF_arr[i]    := 0.0;
        rPosCmdOut_arr[i] := rPosCmd_arr[i];
    ELSE
        // 跟踪误差
        rTrackErr := rPosCmd_arr[i] - rPosFb_arr[i];

        // 同步误差(按模式)
        CASE eCouplingMode OF
            E_ILC_CouplingMode.INDEPENDENT:
                rSyncErr := 0.0;
            E_ILC_CouplingMode.RIGID_SYNC:
                rSyncErr := rPosFb_arr[i] - rMean;
            E_ILC_CouplingMode.PARALLEL_MECH:
                rSyncErr := rPosFb_arr[i] - rSyncRef_arr[i];
        ELSE
            rSyncErr := 0.0;
        END_CASE

        // 综合学习误差(交叉耦合核心)
        // 注:同步误差以反号方式注入 — 同步误差>0表示本缸超前于群体,
        //    应降低前馈量,故综合误差减去 λ·sync
        rCombinedErr := rTrackErr - rSyncCoupling * rSyncErr;

        // 暖机后才记录到本周期误差缓存(用于下周期FF表更新)
        IF iIterCount >= nWarmupCycles THEN
            rErrCapture[i, iPointIndex] := rCombinedErr;
        END_IF

        // 统计累计
        rTrackErrSum2[i] := rTrackErrSum2[i] + rTrackErr * rTrackErr;
        rSyncErrSum2[i]  := rSyncErrSum2[i]  + rSyncErr  * rSyncErr;
        rAbsTrk  := ABS(rTrackErr);
        rAbsSync := ABS(rSyncErr);
        IF rAbsTrk  > rPeakTrkAbs[i]  THEN rPeakTrkAbs[i]  := rAbsTrk;  END_IF
        IF rAbsSync > rPeakSyncAbs[i] THEN rPeakSyncAbs[i] := rAbsSync; END_IF

        // 输出:ILC前馈 + 速度前馈(暖机期只有速度FF)
        IF iIterCount >= nWarmupCycles THEN
            rILC_FF_arr[i] := rFF_Table[i, iPointIndex]
                            + rVelFFGain * rVelCmd_arr[i];
        ELSE
            rILC_FF_arr[i] := rVelFFGain * rVelCmd_arr[i];
        END_IF
        rPosCmdOut_arr[i] := rPosCmd_arr[i] + rILC_FF_arr[i];
    END_IF
END_FOR

iSampleCount := iSampleCount + 1;

END_FUNCTION_BLOCK
