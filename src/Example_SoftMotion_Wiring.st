// ============================================================
// File   : Example_SoftMotion_Wiring.st
// 用途   : 展示 FB_CrossCoupledILC 如何与CODESYS SoftMotion集成
//          - SoftMotion主轴生成位置/速度轨迹
//          - ILC作为前馈修正注入到 SMC_ControlAxisByPos 之前
//          - 位置环PID由用户/SoftMotion底层闭环
// ============================================================

PROGRAM PRG_SoftMotion_ILC_Wiring
VAR
    // ---- SoftMotion 主时钟与从轴 ----
    fbMaster        : MC_VirtualAxis;          // 虚拟主轴(生成相位)
    aSlaves         : ARRAY[1..6] OF AXIS_REF; // 6个伺服阀对应的虚拟从轴
    aCamProfile     : MC_CAM_REF;              // 凸轮曲线(脉冲波形)

    // ---- ILC 输入/输出缓冲 ----
    aPosCmd         : ARRAY[1..200] OF REAL;
    aVelCmd         : ARRAY[1..200] OF REAL;
    aPosFb          : ARRAY[1..200] OF REAL;
    aSyncRef        : ARRAY[1..200] OF REAL;
    aChEnable       : ARRAY[1..200] OF BOOL;
    aPosCmdOut      : ARRAY[1..200] OF REAL;

    // ---- 相位/周期生成 ----
    rMasterPos      : REAL;
    rMasterPosPrev  : REAL;
    rPhase01        : REAL;                    // 0.0 ~ 1.0 归一化相位
    iPhaseIdx       : INT;
    bNewCycle       : BOOL;
    iPointsPerCycle : INT := 1000;             // 1000点/周期
    rPulseHz        : REAL := 2.0;             // 2Hz脉冲
    rCycleLen       : REAL := 360.0;           // 主轴一圈360度

    // ---- ILC 实例 ----
    fbILC           : FB_CrossCoupledILC;
    i               : INT;
END_VAR

// ============================================================
// 1. SoftMotion 主轴生成位置/速度
//    实际工程中,这部分由 MC_CamIn / MC_MoveAbsolute 等FB完成
//    此处仅示意接口
// ============================================================
// 假设 fbMaster.fActPosition 在每周期内 0 → rCycleLen 循环递增
rMasterPos := fbMaster.fActPosition;

// ---- 1.1 计算归一化相位与采样点序号 ----
IF rCycleLen > 0.001 THEN
    rPhase01 := rMasterPos / rCycleLen;
ELSE
    rPhase01 := 0.0;
END_IF
WHILE rPhase01 >= 1.0 DO rPhase01 := rPhase01 - 1.0; END_WHILE
WHILE rPhase01 <  0.0 DO rPhase01 := rPhase01 + 1.0; END_WHILE
iPhaseIdx := REAL_TO_INT(rPhase01 * INT_TO_REAL(iPointsPerCycle));
IF iPhaseIdx >= iPointsPerCycle THEN iPhaseIdx := iPointsPerCycle - 1; END_IF

// ---- 1.2 新周期检测(主轴位置回卷)----
bNewCycle := (rMasterPos < rMasterPosPrev);
rMasterPosPrev := rMasterPos;

// ============================================================
// 2. 从每个从轴读取SoftMotion生成的位置/速度指令 + 反馈
// ============================================================
FOR i := 1 TO 6 DO
    aPosCmd[i]    := aSlaves[i].fSetPosition;        // SoftMotion生成的目标位置
    aVelCmd[i]    := aSlaves[i].fSetVelocity;        // SoftMotion生成的目标速度
    aPosFb[i]     := aSlaves[i].fActPosition;        // 实际反馈位置
    aChEnable[i]  := aSlaves[i].bRegulatorOn;
END_FOR

// ============================================================
// 3. 调用 ILC,得到修正后位置指令
// ============================================================
fbILC(
    bEnable          := TRUE,
    bReset           := FALSE,
    iNumCylinders    := 6,
    iPointsPerCycle  := iPointsPerCycle,
    eCouplingMode    := E_ILC_CouplingMode.RIGID_SYNC,
    iPointIndex      := iPhaseIdx,
    bNewCycle        := bNewCycle,
    rPosCmd_arr      := aPosCmd,
    rVelCmd_arr      := aVelCmd,
    rPosFb_arr       := aPosFb,
    bChannelEnable   := aChEnable,
    rSyncRef_arr     := aSyncRef,
    rLearningGain    := 0.25,
    rSyncCoupling    := 0.7,
    rForgetting      := 0.99,
    rVelFFGain       := 0.0001,             // 速度前馈(小心调,通常很小)
    rFF_Limit        := 2.0,
    rConvergeTol     := 0.02,
    rSafetyTol       := 0.3,
    nWarmupCycles    := 5,
    iPhaseLead       := 3,
    rQFilterStrength := 0.5,
    iUpdateChunkSize := 0,
    rPosCmdOut_arr   => aPosCmdOut
);

// ============================================================
// 4. 把ILC修正后的位置指令"注入"SoftMotion位置环
//    方法A: 覆写从轴 setpoint(适合通过 SMC_ControlAxisByPos 手动控制位置环)
//    方法B: 用 MC_SetOverride / 外部修正接口(具体取决于SoftMotion版本)
//    示意采用方法A
// ============================================================
FOR i := 1 TO 6 DO
    // 直接把ILC输出注入到伺服阀的位置环setpoint
    // 注:这里假设有一个 SMC_ControlAxisByPos 类型的FB或自定义位置环
    //     接管了原来 SoftMotion 的位置控制
    aSlaves[i].fSetPosition := aPosCmdOut[i];
END_FOR

// ============================================================
// 5. 监控/HMI(可选)
// ============================================================
// fbILC.eState           → HMI 显示状态(暖机/学习中/已收敛/故障)
// fbILC.rMaxSyncError    → HMI 同步误差表盘
// fbILC.rGlobalRmsError  → HMI 收敛曲线
// fbILC.aChannelStats[i] → 每缸明细
END_PROGRAM
